"""End-to-end backend tests.

These tests exercise the real API, real preprocessing pipeline, real model
training on a generated dataset and real artifact generation. The dataset is
synthetic but clearly treated as such; no production result is claimed.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app


def _dataset_frame() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    families = ["Normal"] * 500 + ["flood"] * 120 + ["port_scan"] * 120 + ["exfiltration"] * 120
    rng.shuffle(families)
    rows = []
    for index, family in enumerate(families):
        packet_rate = 52.0 if family == "Normal" else {"flood": 390.0, "port_scan": 105.0, "exfiltration": 74.0}[family]
        bytes_rate = 9_500.0 if family == "Normal" else {"flood": 40_000.0, "port_scan": 6_200.0, "exfiltration": 82_000.0}[family]
        connections = 5 if family == "Normal" else {"flood": 15, "port_scan": 31, "exfiltration": 7}[family]
        failures = 0.0 if family != "port_scan" else 6.0
        rows.append(
            {
                "flow_id": f"flow-{index}",
                "src_ip": f"10.10.0.{index % 13}",
                "dst_ip": f"10.10.1.{index % 7}",
                "pkt_rate": max(0.0, packet_rate * rng.normal(1.0, 0.09)),
                "bytes_rate": max(0.0, bytes_rate * rng.normal(1.0, 0.11)),
                "conn_count": max(1.0, connections * rng.normal(1.0, 0.13)),
                "failed_auth": max(0.0, rng.normal(0.0, 0.25) + failures),
                "cpu_usage": min(100.0, (28.0 if family == "Normal" else 54.0) + rng.normal(0, 3.5)),
                "mem_usage": min(100.0, (41.0 if family == "Normal" else 59.0) + rng.normal(0, 4.0)),
                "protocol": rng.choice(["tcp", "udp", "mqtt"], p=[0.5, 0.25, 0.25]),
                "Label": family,
            }
        )
    frame = pd.DataFrame(rows)
    return pd.concat([frame, frame.head(6)], ignore_index=True)


CSV_BYTES = _dataset_frame().to_csv(index=False).encode("utf-8")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def dataset(client):
    response = client.post(
        "/api/datasets/upload",
        files={"file": ("edgeguard_test_iot.csv", CSV_BYTES, "text/csv")},
    )
    assert response.status_code == 201, response.text
    record = response.json()
    client.patch(f"/api/datasets/{record['id']}/target", json={"target_column": "Label"})
    return record


@pytest.fixture(scope="module")
def preprocess_run(client, dataset):
    response = client.post(
        "/api/preprocess/runs",
        json={
            "dataset_id": dataset["id"],
            "target_column": "Label",
            "test_size": 0.25,
            "val_size": 0.15,
            "random_state": 7,
            "max_rows": 5000,
        },
    )
    assert response.status_code == 202, response.text
    job = response.json()["job"]
    assert job["status"] == "completed", job
    run_id = job["result"]["id"]
    return client.get(f"/api/preprocess/runs/{run_id}").json()


@pytest.fixture(scope="module")
def experiment(client, preprocess_run):
    response = client.post(
        "/api/experiments",
        json={
            "preprocess_id": preprocess_run["id"],
            "model_name": "random_forest",
            "params": {"n_estimators": 60},
        },
    )
    assert response.status_code == 202, response.text
    job = response.json()["job"]
    assert job["status"] == "completed", job
    return client.get(f"/api/experiments/{job['result']['id']}").json()


@pytest.fixture(scope="module")
def unknown_experiment(client, preprocess_run):
    response = client.post(
        "/api/unknown/experiments",
        json={
            "preprocess_id": preprocess_run["id"],
            "mode": "holdout",
            "holdout_families": ["exfiltration"],
            "n_estimators": 60,
            "anomaly_estimators": 60,
        },
    )
    assert response.status_code == 202, response.text
    job = response.json()["job"]
    assert job["status"] == "completed", job
    return client.get(f"/api/experiments/{job['result']['id']}").json()


def test_health_and_model_catalog(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    payload = health.json()
    assert payload["status"] == "ok"
    assert "simulated" in payload["scope"].lower()
    models = client.get("/api/models").json()
    keys = {model["key"] for model in models}
    assert {"random_forest", "decision_tree", "logistic_regression", "isolation_forest"} <= keys


def test_dataset_profiling_and_versioning(client, dataset):
    assert dataset["rows"] == len(_dataset_frame())
    assert dataset["target_column"] == "Label"
    assert dataset["duplicates"] == 6
    assert dataset["class_distribution"].get("Normal") >= 500
    assert "Label" in dataset["columns"]

    second = client.post(
        "/api/datasets/upload",
        files={"file": ("edgeguard_test_iot.csv", CSV_BYTES, "text/csv")},
    )
    assert second.status_code == 201
    assert second.json()["version"] == 2
    assert second.json()["parent_id"] == dataset["id"]
    assert client.delete(f"/api/datasets/{second.json()['id']}").status_code == 204


def test_invalid_target_is_rejected(client, dataset):
    response = client.patch(f"/api/datasets/{dataset['id']}/target", json={"target_column": "missing_column"})
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_preprocessing_is_leakage_safe(preprocess_run):
    stats = preprocess_run["stats"]
    split = stats["split"]
    assert split["train_rows"] > 0 and split["val_rows"] > 0 and split["test_rows"] > 0
    assert split["train_rows"] + split["val_rows"] + split["test_rows"] == stats["after"]["rows"]
    assert stats["removed"]["duplicates"] == 6
    assert "flow_id" in stats["removed"]["identifier_columns"]
    assert "src_ip" in stats["removed"]["identifier_columns"]
    assert stats["after"]["features"] > 0
    assert len(stats["leakage_controls"]) >= 5
    assert set(stats["attack_families"]) == {"flood", "port_scan", "exfiltration"}
    assert preprocess_run["test_rows"] == split["test_rows"]


def test_training_metrics_are_derived_from_test_predictions(experiment, preprocess_run):
    metrics = experiment["metrics"]
    assert experiment["status"] == "completed"
    for key in ("accuracy", "precision", "recall", "f1", "false_positive_rate", "roc_auc"):
        assert metrics.get(key) is not None
    assert metrics["n_test"] == preprocess_run["test_rows"]
    assert metrics["tn"] + metrics["fp"] + metrics["fn"] + metrics["tp"] == metrics["n_test"]
    expected_accuracy = (metrics["tn"] + metrics["tp"]) / metrics["n_test"]
    assert abs(metrics["accuracy"] - expected_accuracy) < 1e-6
    assert metrics["model_size_bytes"] > 0
    assert metrics["inference_latency_ms_mean"] >= 0
    assert experiment["artifact_saved"] is True
    assert experiment["predictions_available"] is True
    assert experiment["curves"]["roc"]
    assert experiment["per_class"]


def test_prediction_uses_saved_artifact(client, experiment):
    frame = _dataset_frame().drop(columns=["Label"]).head(5)
    buffer = io.BytesIO()
    frame.to_csv(buffer, index=False)
    response = client.post(
        f"/api/experiments/{experiment['id']}/predict",
        files={"file": ("features.csv", buffer.getvalue(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scored_rows"] == 5
    assert 0 <= payload["flagged"] <= 5
    assert payload["threshold"] == 0.5
    assert all(0 <= row["score"] <= 1 for row in payload["predictions"])


def test_unknown_attack_holdout_excludes_family(unknown_experiment, preprocess_run):
    metrics = unknown_experiment["metrics"]
    assert unknown_experiment["status"] == "completed"
    assert metrics["mode"] == "holdout"
    assert "exfiltration" in metrics["heldout_families"]
    assert metrics["n_unknown"] > 0
    assert metrics["n_known"] > 0
    assert metrics["unknown_attack_recall"] is not None
    assert metrics["known_attack_recall"] is not None
    assert 0.0 <= metrics["benign_false_positive_rate"] <= 1.0
    assert len(unknown_experiment["curves"]["score_histogram"]) == 20
    assert unknown_experiment["per_family"]
    assert unknown_experiment["artifact_saved"] is True


def test_simulated_containment_and_recovery(client, unknown_experiment):
    response = client.post(
        "/api/containment/simulate",
        json={"experiment_id": unknown_experiment["id"], "max_events": 5},
    )
    assert response.status_code == 202, response.text
    job = response.json()["job"]
    assert job["status"] == "completed", job.get("error")

    status = client.get("/api/containment/status").json()
    assert status["devices"]
    assert status["events"]
    event = status["events"][0]
    assert event["action"] in {"OBSERVE", "RATE_LIMIT", "REAUTHENTICATE", "QUARANTINE"}
    assert event["verification"] in {"SUCCESS", "FAILURE", "INCONCLUSIVE"}
    stages = {stage["key"]: stage["count"] for stage in status["pipeline"]["stages"]}
    assert stages["MONITOR"] > 0
    assert stages["DETECT"] > 0

    verified = client.post(f"/api/containment/events/{event['id']}/verify")
    assert verified.status_code == 200
    assert verified.json()["verification"]["verification"] in {"SUCCESS", "FAILURE", "INCONCLUSIVE"}

    released = client.post(f"/api/containment/events/{event['id']}/release")
    assert released.status_code == 200
    assert released.json()["status"] == "RELEASED"


def test_resource_budget_and_benchmark(client, experiment):
    response = client.patch("/api/resources/edge-budget", json={"cpu_capacity": 0.36, "memory_capacity_mb": 128})
    assert response.status_code == 200
    assert response.json()["budget"]["cpu_capacity"] == 0.36
    resources = client.get("/api/resources").json()
    assert resources["host"]["source"] == "measured"
    assert resources["edge"]["source"] == "simulated"
    assert resources["edge"]["budget"]["cpu_capacity"] == 0.36

    benchmark = client.post(
        "/api/resources/benchmark",
        json={"experiment_id": experiment["id"], "sample_size": 40},
    )
    assert benchmark.status_code == 202
    job = benchmark.json()["job"]
    assert job["status"] == "completed", job.get("error")
    measured = job["result"]["measured"]
    assert measured["latency_mean_ms"] > 0
    assert measured["throughput_records_per_sec"] > 0
    assert measured["model_size_bytes"] > 0
    assert measured["records_scored"] == 40


def test_report_exports_and_documentation(client, experiment, unknown_experiment):
    report = client.post("/api/reports", json={"experiment_id": unknown_experiment["id"]})
    assert report.status_code == 201, report.text
    report_id = report.json()["id"]
    download = client.get(f"/api/reports/{report_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF")

    csv_export = client.get(f"/api/analytics/export?experiment_id={experiment['id']}&format=csv")
    assert csv_export.status_code == 200
    assert b"accuracy" in csv_export.content
    json_export = client.get(f"/api/analytics/export?experiment_id={experiment['id']}&format=json")
    assert json_export.status_code == 200
    assert json_export.json()["experiment"]["id"] == experiment["id"]

    docs = client.get("/api/documentation").json()
    assert len(docs["sections"]) >= 12
    assert docs["references"]

    command = client.get("/api/command-center").json()
    assert command["counts"]["datasets"] >= 1
    assert command["counts"]["completed_experiments"] >= 2
    assert command["latest_predictions"]["total_records"] > 0
