"""Seed a clearly labelled synthetic demo through the public API.

This is not research data. It exists only to render populated screenshots and
downloadable example artifacts for the project demonstration.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA_DIR = ROOT / "data" / "showcase"
ARTIFACTS = ROOT / "artifacts"
shutil.rmtree(DATA_DIR, ignore_errors=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS.mkdir(parents=True, exist_ok=True)

os.environ["EDGEGUARD_DATA_DIR"] = str(DATA_DIR)
os.environ["EDGEGUARD_DB_PATH"] = str(DATA_DIR / "edgeguard.sqlite3")
os.environ["EDGEGUARD_SYNC_JOBS"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


def dataset_frame() -> pd.DataFrame:
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


def completed_job(response, label: str):
    assert response.status_code == 202, f"{label}: {response.status_code} {response.text}"
    job = response.json()["job"]
    assert job["status"] == "completed", f"{label}: {job.get('error') or job}"
    return job


def main() -> None:
    frame = dataset_frame()
    csv_bytes = frame.to_csv(index=False).encode("utf-8")
    summary: dict = {"scope": "synthetic demonstration only - not research data"}

    with TestClient(app) as client:
        upload = client.post(
            "/api/datasets/upload",
            files={"file": ("SYNTHETIC_DEMO_NOT_RESEARCH_DATA.csv", csv_bytes, "text/csv")},
        )
        assert upload.status_code == 201, upload.text
        dataset = upload.json()
        assert client.patch(f"/api/datasets/{dataset['id']}/target", json={"target_column": "Label"}).status_code == 200
        dataset = client.get(f"/api/datasets/{dataset['id']}").json()
        summary["dataset"] = {
            "name": dataset["name"],
            "rows": dataset["rows"],
            "columns": len(dataset["columns"]),
            "duplicates": dataset["duplicates"],
            "class_distribution": dataset["class_distribution"],
        }

        pre = completed_job(
            client.post(
                "/api/preprocess/runs",
                json={
                    "dataset_id": dataset["id"],
                    "target_column": "Label",
                    "test_size": 0.25,
                    "val_size": 0.15,
                    "random_state": 7,
                    "max_rows": 5000,
                },
            ),
            "preprocessing",
        )
        run_id = pre["result"]["id"]
        run = client.get(f"/api/preprocess/runs/{run_id}").json()
        summary["preprocessing"] = {
            "id": run_id,
            "after_rows": run["stats"]["after"]["rows"],
            "features": run["stats"]["after"]["features"],
            "split": run["stats"]["split"],
            "removed": run["stats"]["removed"],
        }

        unknown_job = completed_job(
            client.post(
                "/api/unknown/experiments",
                json={
                    "preprocess_id": run_id,
                    "mode": "holdout",
                    "holdout_families": ["exfiltration"],
                    "n_estimators": 80,
                    "anomaly_estimators": 80,
                },
            ),
            "unknown study",
        )
        unknown_id = unknown_job["result"]["id"]

        train_specs = [
            ("decision_tree", {"max_depth": 10, "min_samples_leaf": 2}),
            ("logistic_regression", {"C": 1.0, "max_iter": 1500}),
            ("random_forest", {"n_estimators": 120, "min_samples_leaf": 1}),
        ]
        experiments = []
        for model_name, params in train_specs:
            job = completed_job(
                client.post(
                    "/api/experiments",
                    json={"preprocess_id": run_id, "model_name": model_name, "params": params},
                ),
                model_name,
            )
            experiments.append(job["result"]["id"])

        rf_id = experiments[-1]
        rf = client.get(f"/api/experiments/{rf_id}").json()
        unknown = client.get(f"/api/experiments/{unknown_id}").json()

        completed_job(
            client.post("/api/containment/simulate", json={"experiment_id": rf_id, "max_events": 7}),
            "containment",
        )
        containment = client.get("/api/containment/status").json()
        events = containment["events"]
        if events:
            client.post(f"/api/containment/events/{events[0]['id']}/verify")
        containment = client.get("/api/containment/status").json()
        events = containment["events"]
        outcomes = {}
        for event in events:
            outcomes[event["verification"]] = outcomes.get(event["verification"], 0) + 1

        completed_job(
            client.post("/api/resources/benchmark", json={"experiment_id": rf_id, "sample_size": 80}),
            "benchmark",
        )

        report = client.post("/api/reports", json={"experiment_id": rf_id})
        assert report.status_code == 201, report.text
        report_id = report.json()["id"]
        pdf = client.get(f"/api/reports/{report_id}/download")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        (ARTIFACTS / "showcase-report.pdf").write_bytes(pdf.content)

        csv_export = client.get(f"/api/analytics/export?experiment_id={rf_id}&format=csv")
        assert csv_export.status_code == 200
        (ARTIFACTS / "showcase-metrics.csv").write_bytes(csv_export.content)
        json_export = client.get(f"/api/analytics/export?experiment_id={rf_id}&format=json")
        assert json_export.status_code == 200
        (ARTIFACTS / "showcase-metrics.json").write_bytes(json_export.content)

        command = client.get("/api/command-center").json()
        resources = client.get("/api/resources").json()

        summary["experiments"] = {
            "unknown": {
                "id": unknown_id,
                "known_attack_recall": unknown["metrics"].get("known_attack_recall"),
                "unknown_attack_recall": unknown["metrics"].get("unknown_attack_recall"),
                "benign_false_positive_rate": unknown["metrics"].get("benign_false_positive_rate"),
                "heldout_families": unknown["metrics"].get("heldout_families"),
            },
            "random_forest": {
                "id": rf_id,
                "accuracy": rf["metrics"].get("accuracy"),
                "precision": rf["metrics"].get("precision"),
                "recall": rf["metrics"].get("recall"),
                "f1": rf["metrics"].get("f1"),
                "roc_auc": rf["metrics"].get("roc_auc"),
                "n_test": rf["metrics"].get("n_test"),
                "inference_latency_ms_mean": rf["metrics"].get("inference_latency_ms_mean"),
                "model_size_bytes": rf["metrics"].get("model_size_bytes"),
            },
            "all_ids": experiments,
        }
        summary["containment"] = {
            "events": len(events),
            "outcomes": outcomes,
            "actions": sorted({event["action"] for event in events}),
            "pipeline": {stage["key"]: stage["count"] for stage in containment["pipeline"]["stages"]},
        }
        summary["resources"] = {
            "host_cpu_percent": resources["host"]["host_cpu_percent"],
            "host_memory_percent": resources["host"]["host_memory_percent"],
            "edge_budget": resources["edge"]["budget"],
        }
        summary["command_center"] = command["counts"]
        summary["report"] = {"id": report_id, "bytes": len(pdf.content)}
        summary["exports"] = ["artifacts/showcase-report.pdf", "artifacts/showcase-metrics.csv", "artifacts/showcase-metrics.json"]

    (ARTIFACTS / "showcase-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
