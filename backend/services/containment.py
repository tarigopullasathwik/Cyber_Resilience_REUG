"""Simulated autonomous containment: MONITOR -> DETECT -> ASSESS -> CONTAIN ->
VERIFY -> LEARN.

Nothing here touches the host network. Every device is a simulated object, and
every action changes only the simulator's own state. Verification is performed
by re-scoring real held-out dataset rows through the trained model with the
traffic allowance of the simulated action applied to volume features.
"""

from __future__ import annotations

import math
import re
import warnings
import zlib
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .. import db, settings
from ..jobs import Job
from . import modeling, preprocessing, resources

ACTION_LEVELS = ("OBSERVE", "RATE_LIMIT", "REAUTHENTICATE", "QUARANTINE")
ACTION_ALLOWANCE = {"OBSERVE": 1.0, "RATE_LIMIT": 0.35, "REAUTHENTICATE": 0.10, "QUARANTINE": 0.0}
ACTION_COST = {"OBSERVE": 0.010, "RATE_LIMIT": 0.045, "REAUTHENTICATE": 0.090, "QUARANTINE": 0.140}
ACTION_DEVICE_STATUS = {
    "OBSERVE": "MONITORED",
    "RATE_LIMIT": "THROTTLED",
    "REAUTHENTICATE": "REAUTH_REQUIRED",
    "QUARANTINE": "QUARANTINED",
}
CRITICALITY = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}
VOLUME_COLUMN = re.compile(
    r"(pkt|packet|byte|octet|flow.?byt|rate|bandwidth|duration|conn|count|tot|sum|iat)", re.I
)
RESOURCE_COLUMN = re.compile(r"(cpu|mem|load|util)", re.I)
IP_COLUMN = re.compile(r"(src|source).*ip|^ip$|^src$", re.I)


class ContainmentError(ValueError):
    pass


def _parse_json(value: str | None, fallback: Any) -> Any:
    return db.parse_json(value, fallback)


def list_devices() -> list[dict[str, Any]]:
    return db.query_all("SELECT * FROM devices ORDER BY id")


def list_events(limit: int = 100) -> list[dict[str, Any]]:
    rows = db.query_all(
        "SELECT * FROM containment_events ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    events = []
    for row in rows:
        event = dict(row)
        event["metadata"] = _parse_json(row.get("metadata_json"), {})
        events.append(event)
    return events


def _latest_prediction_experiment(experiment_id: str | None) -> dict[str, Any]:
    if experiment_id:
        row = modeling.get_experiment_row(experiment_id)
    else:
        row = db.query_one(
            "SELECT * FROM experiments WHERE status = 'completed' AND predictions_path IS NOT NULL"
            " ORDER BY completed_at DESC LIMIT 1"
        )
        if not row:
            raise ContainmentError(
                "No completed experiment with test predictions is available. Train a model first."
            )
    if not row.get("predictions_path") or not Path(row["predictions_path"]).exists():
        raise ContainmentError("The selected experiment has no saved test predictions.")
    return row


def _artifact_scoring(artifact: dict[str, Any], prefer_anomaly: bool = False) -> Any:
    if artifact.get("kind") == "unknown":
        supervised = artifact["supervised"]
        anomaly = artifact["anomaly"]
        low, high = float(artifact["norm_low"]), float(artifact["norm_high"])

        def score(matrix: np.ndarray) -> np.ndarray:
            anom = modeling.normalize_scores(modeling._raw_scores(anomaly, matrix), low, high)
            if prefer_anomaly:
                return anom
            sup = np.asarray(supervised.predict_proba(matrix))[:, 1]
            return np.maximum(sup, anom)

        return score
    model = artifact["model"]
    if artifact["score_kind"] == "probability":
        return lambda matrix: np.asarray(model.predict_proba(matrix))[:, 1]
    low, high = float(artifact["norm_low"]), float(artifact["norm_high"])
    return lambda matrix: modeling.normalize_scores(
        modeling._raw_scores(model, matrix), low, high
    )


def _device_map(raw_test: pd.DataFrame) -> list[str]:
    devices = [row["id"] for row in db.query_all("SELECT id FROM devices ORDER BY id")]
    if not devices:
        raise ContainmentError("The simulated device fleet is empty.")
    ip_columns = [column for column in raw_test.columns if IP_COLUMN.search(str(column))]
    mapping: list[str] = []
    for index, row in raw_test.reset_index(drop=True).iterrows():
        if ip_columns:
            value = str(row[ip_columns[0]])
            bucket = zlib.crc32(value.encode("utf-8")) % len(devices)
        else:
            bucket = index % len(devices)
        mapping.append(devices[bucket])
    return mapping


def _severity(score: float, threshold: float, criticality: str, context: float) -> dict[str, float]:
    magnitude = max(0.0, min(1.0, (score - threshold) / max(1.0 - threshold, 1e-9)))
    confidence = max(0.0, min(1.0, score))
    crit = CRITICALITY.get(criticality, 0.5)
    severity = 100.0 * (
        0.35 * magnitude + 0.25 * confidence + 0.20 * crit + 0.20 * context
    )
    risk = min(100.0, severity * (0.55 + 0.45 * confidence))
    return {
        "magnitude": round(magnitude, 4),
        "confidence": round(confidence, 4),
        "criticality": crit,
        "context": round(context, 4),
        "severity": round(severity, 2),
        "risk": round(risk, 2),
    }


def _select_action(
    severity: float, criticality: str, headroom: float, previous_actions: set[str]
) -> tuple[str, str | None]:
    if severity >= 75:
        action = "QUARANTINE"
    elif severity >= 50:
        action = "REAUTHENTICATE"
    elif severity >= 25:
        action = "RATE_LIMIT"
    else:
        action = "OBSERVE"
    note = None
    if action == "QUARANTINE" and criticality == "critical" and severity < 85:
        action = "REAUTHENTICATE"
        note = "critical-asset guard: quarantine requires severity >= 85"
    if action == "QUARANTINE" and not ({"RATE_LIMIT", "REAUTHENTICATE"} & previous_actions):
        action = "REAUTHENTICATE"
        note = "graduated-response guard: a lighter action must fail first"
    level = ACTION_LEVELS.index(action)
    while level > 0 and ACTION_COST[ACTION_LEVELS[level]] > headroom:
        level -= 1
        note = "resource guard downgraded the action to fit the simulated CPU budget"
    return ACTION_LEVELS[level], note


def _volume_columns(bundle: dict[str, Any]) -> list[str]:
    return [
        column for column in bundle["feature_columns"]
        if VOLUME_COLUMN.search(str(column)) and column in bundle["feature_columns"]
    ]


def _score_window(
    artifact: dict[str, Any],
    bundle: dict[str, Any],
    window: pd.DataFrame,
    allowance: float,
) -> tuple[np.ndarray, np.ndarray]:
    pipeline = bundle["pipeline"]
    required = bundle["feature_columns"]
    score = _artifact_scoring(artifact, prefer_anomaly=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        original = pipeline.transform(window[required])
    before = score(np.asarray(original, dtype=np.float32))
    modified = window[required].copy()
    columns = _volume_columns(bundle)
    for column in columns:
        if pd.api.types.is_numeric_dtype(modified[column]):
            modified[column] = modified[column].astype(float) * allowance
    # Simulated effect: containment also dampens attack-driven resource load.
    resource_factor = 0.65 + 0.35 * allowance
    for column in required:
        if RESOURCE_COLUMN.search(str(column)) and pd.api.types.is_numeric_dtype(modified[column]):
            modified[column] = modified[column].astype(float) * resource_factor
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        scaled = pipeline.transform(modified[required])
    after = score(np.asarray(scaled, dtype=np.float32))
    return before, after


def _verify_event(
    event: dict[str, Any], experiment_row: dict[str, Any], device_id: str
) -> dict[str, Any]:
    metadata = _parse_json(event.get("metadata_json"), {})
    allowance = float(metadata.get("allowance", 1.0))
    if allowance >= 1.0:
        return {
            "verification": "INCONCLUSIVE",
            "after_score": None,
            "detail": "Observation-only action; there is no containment effect to verify.",
        }
    run_row = preprocessing.get_run_row(experiment_row["preprocess_id"])
    splits = preprocessing.load_splits(run_row)
    raw_test = splits["test_raw"]
    artifact = modeling.load_artifact(experiment_row["id"])
    bundle = preprocessing.load_preprocessor(run_row)
    if not _volume_columns(bundle):
        return {
            "verification": "INCONCLUSIVE",
            "after_score": None,
            "detail": "No recognised traffic-volume columns were found, so the simulated "
                      "effect of the action cannot be applied to real features.",
        }
    mapping = _device_map(raw_test)
    trigger = int(metadata.get("row_index", 0))
    all_candidates = [
        index for index, mapped in enumerate(mapping)
        if mapped == device_id and index > trigger
    ]
    predictions = pd.read_parquet(experiment_row["predictions_path"])
    score_by_index = predictions.set_index("row_index")["score"].to_dict()
    threshold = float(metadata.get("threshold", 0.5))
    offending = [
        index for index in all_candidates
        if float(score_by_index.get(index, 0.0)) >= threshold
    ]
    candidates = offending[:5]
    if not candidates:
        return {
            "verification": "INCONCLUSIVE",
            "after_score": None,
            "detail": "No subsequent held-out records were still offending for this simulated "
                      "device, so the action's effect cannot be attributed.",
        }
    window = raw_test.iloc[candidates]
    before, after = _score_window(artifact, bundle, window, allowance)
    before_mean = float(np.mean(before))
    after_mean = float(np.mean(after))
    reduction = (before_mean - after_mean) / max(before_mean, 1e-9)
    if before_mean <= 0.20:
        return {
            "verification": "INCONCLUSIVE",
            "after_score": round(after_mean, 6),
            "detail": "Subsequent held-out behaviour was already close to benign; the action "
                      "cannot be credited with a measurable reduction.",
            "window_rows": int(len(window)),
        }
    if after_mean <= 0.20 or reduction >= 0.35:
        verdict = "SUCCESS"
    elif reduction <= 0.05:
        verdict = "FAILURE"
    else:
        verdict = "INCONCLUSIVE"
    return {
        "verification": verdict,
        "after_score": round(after_mean, 6),
        "detail": (
            f"Simulated {metadata.get('action', 'action').lower()} (allowance {allowance:.2f}) "
            f"applied to {len(window)} held-out records of {device_id}: mean anomaly score "
            f"{before_mean:.3f} -> {after_mean:.3f} ({reduction * 100:+.1f}%)."
        ),
        "before_window_mean": round(before_mean, 6),
        "after_window_mean": round(after_mean, 6),
        "reduction": round(reduction, 4),
        "window_rows": int(len(window)),
    }


def simulate(experiment_id: str | None, config: dict[str, Any], job: Job) -> dict[str, Any]:
    experiment_row = _latest_prediction_experiment(experiment_id)
    predictions = pd.read_parquet(experiment_row["predictions_path"])
    if predictions.empty:
        raise ContainmentError("The experiment has no test predictions to replay.")
    run_row = preprocessing.get_run_row(experiment_row["preprocess_id"])
    splits = preprocessing.load_splits(run_row)
    raw_test = splits["test_raw"]
    mapping = _device_map(raw_test)
    devices = {row["id"]: row for row in list_devices()}
    threshold = float(db.parse_json(experiment_row["metrics_json"], {}).get("threshold", 0.5))
    max_events = max(1, min(int(config.get("max_events", 8)), 25))
    context = float((predictions["predicted"] == 1).mean()) if "predicted" in predictions else 0.0
    budget = resources.get_budget()
    headroom = float(resources.edge_snapshot()["simulated_cpu_headroom"])

    job.update(0.1, "MONITOR: replaying held-out test predictions")
    flagged = predictions[predictions["predicted"] == 1].copy()
    flagged = flagged.sort_values("score", ascending=False)
    if flagged.empty:
        return {
            "events": [],
            "message": "The selected experiment flagged no test rows; there is nothing to contain.",
            "pipeline": pipeline_status(),
        }

    chosen: list[pd.Series] = []
    used_devices: set[str] = set()
    for _, row in flagged.iterrows():
        index = int(row["row_index"])
        if index >= len(mapping):
            continue
        device_id = mapping[index]
        if device_id in used_devices:
            continue
        used_devices.add(device_id)
        chosen.append(row)
        if len(chosen) >= max_events:
            break

    created: list[dict[str, Any]] = []
    previous_actions = {
        row["action"] for row in db.query_all(
            "SELECT action FROM containment_events WHERE device_id IN ({})".format(
                ",".join("?" for _ in used_devices)
            ),
            tuple(used_devices),
        )
    } if used_devices else set()

    job.update(0.3, "DETECT: ranking flagged flows")
    for index, row in enumerate(chosen):
        row_index = int(row["row_index"])
        device_id = mapping[row_index]
        device = devices.get(device_id)
        if not device:
            continue
        severity = _severity(
            float(row["score"]), threshold, device["criticality"], context
        )
        action, guard_note = _select_action(
            severity["severity"], device["criticality"], headroom, previous_actions
        )
        previous_actions.add(action)
        headroom = max(0.0, headroom - ACTION_COST[action])
        event_id = db.new_id("ce_")
        metadata = {
            "row_index": row_index,
            "score": round(float(row["score"]), 6),
            "threshold": threshold,
            "action": action,
            "allowance": ACTION_ALLOWANCE[action],
            "guard": guard_note,
            "family": str(row.get("y_family", "unknown")),
            "withheld": bool(row.get("withheld", False)),
            "experiment_id": experiment_row["id"],
            "episode": "historical dataset replay (not live capture)",
        }
        event = {
            "id": event_id,
            "experiment_id": experiment_row["id"],
            "device_id": device_id,
            "device_name": device["name"],
            "action": action,
            "severity": severity["severity"],
            "risk": severity["risk"],
            "confidence": severity["confidence"],
            "status": "ACTIVE",
            "reason": guard_note or f"Anomaly score {float(row['score']):.3f} above threshold {threshold:.3f}",
            "before_score": round(float(row["score"]), 6),
            "after_score": None,
            "verification": None,
            "verification_detail": None,
            "created_at": db.utc_now(),
            "verified_at": None,
            "released_at": None,
            "metadata_json": db.as_json(metadata),
        }
        db.insert("containment_events", event)
        db.update(
            "devices",
            device_id,
            {
                "status": ACTION_DEVICE_STATUS[action],
                "policy_level": ACTION_LEVELS.index(action),
                "last_action": action,
                "last_seen": db.utc_now(),
            },
        )
        created.append(event)
        job.update(0.3 + 0.3 * (index + 1) / max(len(chosen), 1), f"ASSESS: {device['name']} severity {severity['severity']:.0f}")

    job.update(0.65, "VERIFY: re-scoring held-out records under the simulated action")
    verified: list[dict[str, Any]] = []
    for index, event in enumerate(created):
        device_id = event["device_id"]
        result = _verify_event(event, experiment_row, device_id)
        status = "CONTAINED" if result["verification"] == "SUCCESS" else (
            "FAILED" if result["verification"] == "FAILURE" else "ACTIVE"
        )
        db.update(
            "containment_events",
            event["id"],
            {
                "status": status,
                "after_score": result.get("after_score"),
                "verification": result["verification"],
                "verification_detail": result["detail"],
                "verified_at": db.utc_now(),
            },
        )
        event.update(
            {
                "status": status,
                "after_score": result.get("after_score"),
                "verification": result["verification"],
                "verification_detail": result["detail"],
            }
        )
        verified.append(result)
        job.update(0.65 + 0.25 * (index + 1) / max(len(created), 1), f"VERIFY: {event['device_name']} -> {result['verification']}")

    job.update(0.95, "LEARN: recording verified outcomes")
    summary = {
        "events": created,
        "verification": verified,
        "pipeline": pipeline_status(),
        "budget": budget,
        "experiment_id": experiment_row["id"],
        "mode": "historical dataset replay — simulated containment, not live traffic",
    }
    job.update(1.0, f"Containment replay complete: {len(created)} events")
    return summary


def verify_event(event_id: str) -> dict[str, Any]:
    event = db.query_one("SELECT * FROM containment_events WHERE id = ?", (event_id,))
    if not event:
        raise ContainmentError("Containment event not found.")
    experiment_id = event.get("experiment_id")
    if not experiment_id:
        raise ContainmentError("This event is not linked to an experiment.")
    experiment_row = modeling.get_experiment_row(experiment_id)
    result = _verify_event(event, experiment_row, event["device_id"])
    status = "CONTAINED" if result["verification"] == "SUCCESS" else (
        "FAILED" if result["verification"] == "FAILURE" else event["status"]
    )
    db.update(
        "containment_events",
        event_id,
        {
            "status": status,
            "after_score": result.get("after_score"),
            "verification": result["verification"],
            "verification_detail": result["detail"],
            "verified_at": db.utc_now(),
        },
    )
    return {"event": next(item for item in list_events(500) if item["id"] == event_id),
            "verification": result}


def release_event(event_id: str) -> dict[str, Any]:
    event = db.query_one("SELECT * FROM containment_events WHERE id = ?", (event_id,))
    if not event:
        raise ContainmentError("Containment event not found.")
    if event["status"] == "RELEASED":
        return next(item for item in list_events(500) if item["id"] == event_id)
    db.update(
        "containment_events",
        event_id,
        {"status": "RELEASED", "released_at": db.utc_now()},
    )
    db.update(
        "devices",
        event["device_id"],
        {"status": "ACTIVE", "policy_level": 0, "last_action": "RELEASE", "last_seen": db.utc_now()},
    )
    return next(item for item in list_events(500) if item["id"] == event_id)


def pipeline_status() -> dict[str, Any]:
    latest = _latest_prediction_experiment(None) if db.query_one(
        "SELECT id FROM experiments WHERE status = 'completed' AND predictions_path IS NOT NULL LIMIT 1"
    ) else None
    monitored = detected = 0
    if latest:
        try:
            predictions = pd.read_parquet(latest["predictions_path"])
            monitored = int(len(predictions))
            detected = int((predictions["predicted"] == 1).sum())
        except (OSError, ValueError, KeyError):
            pass
    events = db.query_all("SELECT action, status, verification FROM containment_events")
    assessed = len(events)
    contained = sum(1 for event in events if event["status"] == "CONTAINED")
    verified = sum(1 for event in events if event.get("verification") in {"SUCCESS", "FAILURE", "INCONCLUSIVE"})
    learned = sum(1 for event in events if event.get("verification") == "SUCCESS")
    stages = [
        {"key": "MONITOR", "label": "Monitor", "count": monitored,
         "description": "Held-out records replayed through the trained detector."},
        {"key": "DETECT", "label": "Detect", "count": detected,
         "description": "Records whose score crossed the experiment threshold."},
        {"key": "ASSESS", "label": "Assess", "count": assessed,
         "description": "Flows assessed for severity, risk and device criticality."},
        {"key": "CONTAIN", "label": "Contain", "count": sum(1 for e in events if e["action"] != "OBSERVE"),
         "description": "Simulated actions applied to simulated devices."},
        {"key": "VERIFY", "label": "Verify", "count": verified,
         "description": "Re-scored held-out records under the simulated action."},
        {"key": "LEARN", "label": "Learn", "count": learned,
         "description": "Verified outcomes recorded for baseline adaptation review."},
    ]
    return {
        "stages": stages,
        "events": events,
        "latest_experiment": latest["id"] if latest else None,
    }


def status() -> dict[str, Any]:
    return {
        "devices": list_devices(),
        "events": list_events(60),
        "pipeline": pipeline_status(),
        "edge": resources.edge_snapshot(),
        "scope_note": "All devices and actions are simulated. No host network traffic is modified.",
    }


def threats(experiment_id: str | None, threshold: float = 0.5) -> dict[str, Any]:
    row = _latest_prediction_experiment(experiment_id)
    predictions = pd.read_parquet(row["predictions_path"])
    scores = predictions["score"].astype(float)
    labels = predictions.get("y_binary", pd.Series([0] * len(predictions)))
    family = predictions.get("y_family", pd.Series(["unknown"] * len(predictions))).astype(str)
    withheld = predictions.get("withheld", pd.Series([False] * len(predictions))).astype(bool)
    predicted = scores >= threshold
    benign = predictions["y_binary"] == 0
    known = (predictions["y_binary"] == 1) & (~withheld)
    unknown = (predictions["y_binary"] == 1) & withheld
    composition = {
        "benign_records": int((benign & ~predicted).sum()),
        "benign_flagged": int((benign & predicted).sum()),
        "known_detected": int((known & predicted).sum()),
        "known_missed": int((known & ~predicted).sum()),
        "unknown_suspected": int((unknown & predicted).sum()),
        "unknown_missed": int((unknown & ~predicted).sum()),
        "total_records": int(len(predictions)),
    }
    top = predictions.assign(
        predicted=predicted.astype(int), family=family, withheld=withheld
    ).sort_values("score", ascending=False).head(25)
    top_records = [
        {
            "row_index": int(item["row_index"]),
            "score": round(float(item["score"]), 6),
            "predicted": int(item["predicted"]),
            "ground_truth": "malicious" if int(item["y_binary"]) else "benign",
            "family": item["family"],
            "withheld_family": bool(item["withheld"]),
            "classification": (
                "suspected unknown" if item["predicted"] and item["withheld"]
                else "known malicious" if item["predicted"]
                else "benign"
            ),
        }
        for _, item in top.iterrows()
    ]
    family_rows = []
    for name in sorted({value for value in family[labels == 1]}):
        mask = labels == 1
        mask &= family == name
        count = int(mask.sum())
        if count:
            family_rows.append(
                {
                    "family": name,
                    "records": count,
                    "flagged": int(predicted[mask].sum()),
                    "detection_rate": round(float(predicted[mask].mean()), 4),
                    "mean_score": round(float(scores[mask].mean()), 4),
                    "withheld": bool(withheld[mask].any()),
                }
            )
    bins = np.linspace(0, 1, 21)
    histogram = [
        {
            "bin": f"{bins[index]:.2f}",
            "benign": int(((scores[benign] >= bins[index]) & (scores[benign] < bins[index + 1])).sum()),
            "malicious": int(((scores[labels == 1] >= bins[index]) & (scores[labels == 1] < bins[index + 1])).sum()),
        }
        for index in range(len(bins) - 1)
    ]
    return {
        "experiment": modeling.experiment_record(row, include_curves=False),
        "threshold": threshold,
        "composition": composition,
        "top_records": top_records,
        "families": family_rows,
        "score_histogram": histogram,
        "scope_note": (
            "'Suspected unknown' means the record belongs to a withheld attack family in a "
            "leave-family-out experiment. It is not a zero-day claim."
        ),
    }
