"""Resource monitoring.

Two clearly separate sources exist in this module:

* **measured** - psutil readings of the host process and machine running the
  backend, plus wall-clock latency measured while scoring real test rows;
* **simulated** - a configurable edge-device budget (CPU, RAM, uplink) used by
  the containment resource guard. It is not a measurement of any device.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import psutil

from .. import db, settings
from ..jobs import Job
from . import modeling, preprocessing

DEFAULT_BUDGET = {
    "cpu_capacity": 1.0,
    "memory_capacity_mb": 256.0,
    "bandwidth_capacity_kbps": 2048.0,
    "detector_cpu_per_record": 0.006,
    "memory_per_device_mb": 3.2,
    "latency_budget_ms": 25.0,
}


class ResourceError(ValueError):
    pass


def host_snapshot() -> dict[str, Any]:
    process = psutil.Process()
    memory = psutil.virtual_memory()
    cpu_times = process.cpu_times()
    return {
        "source": "measured",
        "host_cpu_percent": round(psutil.cpu_percent(interval=0.08), 2),
        "host_memory_percent": round(memory.percent, 2),
        "host_memory_used_mb": round((memory.total - memory.available) / (1024 * 1024), 1),
        "host_memory_total_mb": round(memory.total / (1024 * 1024), 1),
        "logical_cpus": psutil.cpu_count(logical=True),
        "process_rss_mb": round(process.memory_info().rss / (1024 * 1024), 2),
        "process_cpu_seconds": round(cpu_times.user + cpu_times.system, 2),
        "process_threads": process.num_threads(),
        "uptime_seconds": round(time.time() - psutil.boot_time(), 1),
    }


def get_budget() -> dict[str, float]:
    if settings.EDGE_BUDGET_PATH.exists():
        try:
            payload = json.loads(settings.EDGE_BUDGET_PATH.read_text(encoding="utf-8"))
            return {**DEFAULT_BUDGET, **{key: float(value) for key, value in payload.items()}}
        except (OSError, ValueError, TypeError):
            pass
    return dict(DEFAULT_BUDGET)


def set_budget(payload: dict[str, Any]) -> dict[str, float]:
    budget = get_budget()
    for key, minimum, maximum in (
        ("cpu_capacity", 0.05, 8.0),
        ("memory_capacity_mb", 32.0, 16384.0),
        ("bandwidth_capacity_kbps", 64.0, 1_000_000.0),
        ("detector_cpu_per_record", 0.0005, 0.1),
        ("memory_per_device_mb", 0.5, 256.0),
        ("latency_budget_ms", 1.0, 5000.0),
    ):
        if key in payload and payload[key] is not None:
            value = float(payload[key])
            if not minimum <= value <= maximum:
                raise ResourceError(f"{key} must be between {minimum} and {maximum}.")
            budget[key] = value
    settings.EDGE_BUDGET_PATH.write_text(json.dumps(budget, indent=2), encoding="utf-8")
    return budget


def edge_snapshot() -> dict[str, Any]:
    budget = get_budget()
    active = db.query_all(
        "SELECT action FROM containment_events WHERE status IN ('ACTIVE', 'CONTAINED')"
    )
    action_cost = {"OBSERVE": 0.01, "RATE_LIMIT": 0.045, "REAUTHENTICATE": 0.09, "QUARANTINE": 0.14}
    used = 0.02 + sum(action_cost.get(row["action"], 0.02) for row in active)
    devices = db.query_all("SELECT COUNT(*) AS n FROM devices")[0]["n"]
    simulated_cpu = min(used, budget["cpu_capacity"] * 0.99)
    return {
        "source": "simulated",
        "budget": budget,
        "simulated_cpu_used": round(simulated_cpu, 4),
        "simulated_cpu_utilisation": round(simulated_cpu / max(budget["cpu_capacity"], 1e-9), 4),
        "simulated_cpu_headroom": round(max(budget["cpu_capacity"] - used, 0.0), 4),
        "simulated_memory_used_mb": round(
            min(devices * budget["memory_per_device_mb"] + 24.0, budget["memory_capacity_mb"]), 1
        ),
        "simulated_memory_utilisation": round(
            min((devices * budget["memory_per_device_mb"] + 24.0) / budget["memory_capacity_mb"], 1.0), 4
        ),
        "active_containment_actions": len(active),
        "note": "Simulated edge budget. Not a measurement of physical hardware.",
    }


def _artifact_score_fn(experiment_id: str) -> tuple[Any, list[str]]:
    artifact = modeling.load_artifact(experiment_id)
    if artifact.get("kind") == "unknown":
        supervised = artifact["supervised"]
        anomaly = artifact["anomaly"]
        threshold = float(artifact["threshold"])
        low, high = float(artifact["norm_low"]), float(artifact["norm_high"])

        def score(matrix: np.ndarray) -> np.ndarray:
            supervised_score = np.asarray(supervised.predict_proba(matrix))[:, 1]
            anomaly_score = modeling.normalize_scores(
                modeling._raw_scores(anomaly, matrix), low, high
            )
            return np.maximum(supervised_score, anomaly_score)

        del threshold
        return score, artifact["feature_names"]
    model = artifact["model"]
    if artifact["score_kind"] == "probability":
        return (lambda matrix: np.asarray(model.predict_proba(matrix))[:, 1]), artifact["feature_names"]
    low, high = float(artifact["norm_low"]), float(artifact["norm_high"])
    return (
        lambda matrix: modeling.normalize_scores(modeling._raw_scores(model, matrix), low, high),
        artifact["feature_names"],
    )


def benchmark(experiment_id: str, job: Job, sample_size: int = 120) -> dict[str, Any]:
    row = modeling.get_experiment_row(experiment_id)
    if not row.get("preprocessor_path"):
        raise ResourceError("The experiment has no preprocessing artifact to benchmark.")
    run_row = preprocessing.get_run_row(row["preprocess_id"])
    splits = preprocessing.load_splits(run_row)
    raw_test = splits["test_raw"]
    bundle = preprocessing.load_preprocessor(run_row)
    pipeline = bundle["pipeline"]
    required = bundle["feature_columns"]
    score_fn, _ = _artifact_score_fn(experiment_id)
    sample = raw_test.head(min(sample_size, len(raw_test)))
    if sample.empty:
        raise ResourceError("The test split is empty; nothing to benchmark.")
    process = psutil.Process()
    job.update(0.15, "Warming up the model")
    with __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        first = pipeline.transform(sample[required].head(1))
    score_fn(np.asarray(first, dtype=np.float32))
    timings: list[float] = []
    rss_before = process.memory_info().rss
    cpu_before = process.cpu_times()
    job.update(0.35, f"Scoring {len(sample)} real test rows end to end")
    for index in range(len(sample)):
        start = time.perf_counter()
        with __import__("warnings").catch_warnings():
            __import__("warnings").simplefilter("ignore")
            matrix = pipeline.transform(sample.iloc[[index]][required])
        score_fn(np.asarray(matrix, dtype=np.float32))
        timings.append((time.perf_counter() - start) * 1000.0)
    elapsed = max(sum(timings) / 1000.0, 1e-9)
    rss_after = process.memory_info().rss
    cpu_after = process.cpu_times()
    cpu_seconds = (cpu_after.user + cpu_after.system) - (cpu_before.user + cpu_before.system)
    runtime = {
        "experiment_id": experiment_id,
        "measured": {
            "source": "measured",
            "latency_mean_ms": round(float(np.mean(timings)), 3),
            "latency_p95_ms": round(float(np.percentile(timings, 95)), 3),
            "latency_min_ms": round(float(np.min(timings)), 3),
            "throughput_records_per_sec": round(len(sample) / elapsed, 2),
            "cpu_seconds": round(float(cpu_seconds), 4),
            "cpu_percent_backend": round(100.0 * cpu_seconds / elapsed, 2),
            "rss_delta_mb": round((rss_after - rss_before) / (1024 * 1024), 3),
            "rss_after_mb": round(rss_after / (1024 * 1024), 2),
            "model_size_bytes": int(Path(row["artifact_path"]).stat().st_size),
            "model_size_mb": round(Path(row["artifact_path"]).stat().st_size / (1024 * 1024), 4),
            "records_scored": len(sample),
        },
        "simulated_edge": {
            "source": "simulated",
            **get_budget(),
            "meets_latency_budget": float(np.percentile(timings, 95)) <= get_budget()["latency_budget_ms"],
        },
        "note": (
            "Latency and memory are measured on this backend host. The edge budget is a "
            "simulation parameter and does not describe physical edge hardware."
        ),
    }
    db.insert(
        "resource_samples",
        {
            "id": db.new_id("rs_"),
            "experiment_id": experiment_id,
            "payload_json": db.as_json(runtime),
            "created_at": db.utc_now(),
        },
    )
    job.update(1.0, "Benchmark complete")
    return runtime


def latest_samples(limit: int = 20) -> list[dict[str, Any]]:
    rows = db.query_all(
        "SELECT * FROM resource_samples ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    return [
        {
            "id": row["id"],
            "experiment_id": row["experiment_id"],
            "created_at": row["created_at"],
            "payload": db.parse_json(row["payload_json"], {}),
        }
        for row in rows
    ]


def overview() -> dict[str, Any]:
    return {
        "host": host_snapshot(),
        "edge": edge_snapshot(),
        "latest_samples": latest_samples(6),
        "note": settings.SCOPE_NOTE,
    }

