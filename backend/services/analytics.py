"""Aggregate analytics for the command center and research dashboards."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .. import db
from . import containment, datasets, modeling, resources


def _metric(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = row.get("metrics", {}).get(key)
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def overview() -> dict[str, Any]:
    dataset_rows = db.query_all("SELECT * FROM datasets")
    experiment_rows = db.query_all("SELECT * FROM experiments")
    completed = [modeling.experiment_record(row, include_curves=False) for row in experiment_rows
                 if row["status"] == "completed"]
    latest = next((row for row in completed if row.get("predictions_available")), None)
    predictions_summary = {}
    if latest and latest.get("dataset_id"):
        try:
            import pandas as pd

            row = modeling.get_experiment_row(latest["id"])
            frame = pd.read_parquet(row["predictions_path"])
            predictions_summary = {
                "total_records": int(len(frame)),
                "benign": int((frame["y_binary"] == 0).sum()),
                "malicious": int((frame["y_binary"] == 1).sum()),
                "flagged": int((frame["predicted"] == 1).sum()),
                "unknown_suspected": int(((frame["predicted"] == 1) & (frame.get("withheld", False) == True)).sum())  # noqa: E712
                if "withheld" in frame else 0,
            }
        except Exception:  # noqa: BLE001
            predictions_summary = {}
    events = db.query_all("SELECT status FROM containment_events")
    contained = sum(1 for event in events if event["status"] == "CONTAINED")
    devices = db.query_all("SELECT status FROM devices")
    active = sum(1 for device in devices if device["status"] == "ACTIVE")
    return {
        "counts": {
            "datasets": len(dataset_rows),
            "experiments": len(experiment_rows),
            "completed_experiments": len(completed),
            "preprocess_runs": db.query_one("SELECT COUNT(*) AS n FROM preprocess_runs")["n"],
            "reports": db.query_one("SELECT COUNT(*) AS n FROM reports")["n"],
            "containment_events": len(events),
            "contained_threats": contained,
            "simulated_devices": len(devices),
            "healthy_devices": active,
        },
        "active_model": {
            "id": latest["id"],
            "name": latest["name"],
            "model": latest["model_name"],
            "status": latest["status"],
            "f1": _metric(latest, "f1"),
            "recall": _metric(latest, "recall"),
            "unknown_recall": _metric(latest, "unknown_attack_recall"),
        } if latest else None,
        "latest_predictions": predictions_summary,
        "network_health": round(active / max(len(devices), 1) * 100, 1),
        "devices": containment.list_devices(),
        "latest_events": containment.list_events(8),
        "resources": resources.overview(),
        "recent_experiments": completed[:6],
        "mode_note": (
            "Dashboard values come from stored experiments and historical dataset replay. "
            "No live network capture is claimed."
        ),
    }


def comparison(experiment_ids: list[str] | None = None) -> dict[str, Any]:
    rows = db.query_all("SELECT * FROM experiments WHERE status = 'completed' ORDER BY completed_at DESC")
    records = [modeling.experiment_record(row) for row in rows]
    if experiment_ids:
        selected = [record for record in records if record["id"] in set(experiment_ids)]
    else:
        selected = records[:4]
    table = []
    for record in selected:
        metrics = record["metrics"]
        table.append(
            {
                "id": record["id"],
                "name": record["name"],
                "kind": record["kind"],
                "model": record["model_name"],
                "accuracy": metrics.get("accuracy"),
                "precision": metrics.get("precision"),
                "recall": metrics.get("recall"),
                "f1": metrics.get("f1"),
                "false_positive_rate": metrics.get("false_positive_rate"),
                "roc_auc": metrics.get("roc_auc"),
                "known_recall": metrics.get("known_attack_recall"),
                "unknown_recall": metrics.get("unknown_attack_recall"),
                "lofo_unknown_recall": metrics.get("lofo_mean_unknown_recall"),
                "latency_ms": metrics.get("inference_latency_ms_mean"),
                "throughput": metrics.get("throughput_records_per_sec"),
                "model_size_mb": metrics.get("model_size_mb"),
                "completed_at": record["completed_at"],
            }
        )
    return {"experiments": selected, "table": table}


def metric_series(experiment_id: str) -> dict[str, Any]:
    experiment = modeling.get_experiment(experiment_id)
    return {
        "id": experiment["id"],
        "metrics": experiment["metrics"],
        "curves": experiment.get("curves", {}),
        "per_class": experiment["per_class"],
        "per_family": experiment["per_family"],
        "confusion": experiment["confusion"],
        "feature_importance": experiment["feature_importance"],
    }


def dataset_usage() -> list[dict[str, Any]]:
    rows = db.query_all(
        "SELECT dataset_id, COUNT(*) AS experiments FROM experiments GROUP BY dataset_id"
    )
    counts = Counter({row["dataset_id"]: row["experiments"] for row in rows if row["dataset_id"]})
    return [
        {"dataset_id": dataset["id"], "name": dataset["name"], "experiments": counts.get(dataset["id"], 0)}
        for dataset in datasets.list_datasets()
    ]
