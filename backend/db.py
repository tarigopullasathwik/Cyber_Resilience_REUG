"""SQLite persistence layer.

A connection is opened per operation so the module is safe to use from the
FastAPI thread pool and from background training jobs.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from . import settings

DEVICE_SEED: tuple[dict[str, Any], ...] = (
    {"id": "D-01", "name": "Perimeter Camera", "ip": "10.20.0.11", "type": "IP camera", "criticality": "high"},
    {"id": "D-02", "name": "HVAC Thermostat", "ip": "10.20.0.12", "type": "Thermostat", "criticality": "medium"},
    {"id": "D-03", "name": "Cold Storage Plug", "ip": "10.20.0.13", "type": "Smart plug", "criticality": "low"},
    {"id": "D-04", "name": "Lab Door Lock", "ip": "10.20.0.14", "type": "Door lock", "criticality": "critical"},
    {"id": "D-05", "name": "Energy Meter A", "ip": "10.20.0.15", "type": "Smart meter", "criticality": "high"},
    {"id": "D-06", "name": "Wearable Gateway", "ip": "10.20.0.16", "type": "Wearable", "criticality": "high"},
    {"id": "D-07", "name": "Assembly PLC", "ip": "10.20.0.17", "type": "Industrial PLC", "criticality": "critical"},
    {"id": "D-08", "name": "Reception Assistant", "ip": "10.20.0.18", "type": "Voice assistant", "criticality": "medium"},
    {"id": "D-09", "name": "Zone Light Hub", "ip": "10.20.0.19", "type": "Light controller", "criticality": "low"},
    {"id": "D-10", "name": "Irrigation Node", "ip": "10.20.0.20", "type": "Irrigation sensor", "criticality": "medium"},
    {"id": "D-11", "name": "Firmware Mirror", "ip": "10.20.0.21", "type": "Edge cache", "criticality": "high"},
    {"id": "D-12", "name": "Backup Gateway", "ip": "10.20.0.22", "type": "Gateway", "criticality": "critical"},
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    parent_id TEXT,
    origin TEXT NOT NULL DEFAULT 'upload',
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    format TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    rows INTEGER NOT NULL DEFAULT 0,
    cols INTEGER NOT NULL DEFAULT 0,
    target_column TEXT,
    columns_json TEXT NOT NULL DEFAULT '[]',
    dtypes_json TEXT NOT NULL DEFAULT '{}',
    missing_json TEXT NOT NULL DEFAULT '{}',
    duplicates INTEGER NOT NULL DEFAULT 0,
    class_distribution_json TEXT NOT NULL DEFAULT '{}',
    target_candidates_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'ready',
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preprocess_runs (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    name TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    stats_json TEXT NOT NULL DEFAULT '{}',
    artifact_path TEXT NOT NULL,
    preprocessor_path TEXT NOT NULL,
    target_column TEXT,
    feature_names_json TEXT NOT NULL DEFAULT '[]',
    families_json TEXT NOT NULL DEFAULT '[]',
    train_rows INTEGER NOT NULL DEFAULT 0,
    val_rows INTEGER NOT NULL DEFAULT 0,
    test_rows INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    dataset_id TEXT,
    preprocess_id TEXT,
    model_name TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    curves_json TEXT NOT NULL DEFAULT '{}',
    confusion_json TEXT NOT NULL DEFAULT '{}',
    per_class_json TEXT NOT NULL DEFAULT '[]',
    per_family_json TEXT NOT NULL DEFAULT '[]',
    feature_importance_json TEXT NOT NULL DEFAULT '[]',
    artifact_path TEXT,
    preprocessor_path TEXT,
    predictions_path TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    progress REAL NOT NULL DEFAULT 0,
    message TEXT,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS containment_events (
    id TEXT PRIMARY KEY,
    experiment_id TEXT,
    device_id TEXT NOT NULL,
    device_name TEXT,
    action TEXT NOT NULL,
    severity REAL NOT NULL DEFAULT 0,
    risk REAL NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    reason TEXT,
    before_score REAL,
    after_score REAL,
    verification TEXT,
    verification_detail TEXT,
    created_at TEXT NOT NULL,
    verified_at TEXT,
    released_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ip TEXT NOT NULL,
    type TEXT NOT NULL,
    criticality TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    policy_level INTEGER NOT NULL DEFAULT 0,
    last_action TEXT,
    last_seen TEXT,
    baseline_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    experiment_id TEXT,
    title TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT 'pdf',
    path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resource_samples (
    id TEXT PRIMARY KEY,
    experiment_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    value = uuid.uuid4().hex[:18]
    return f"{prefix}{value}" if prefix else value


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        existing = {row["id"] for row in conn.execute("SELECT id FROM devices")}
        for device in DEVICE_SEED:
            if device["id"] not in existing:
                conn.execute(
                    "INSERT INTO devices (id, name, ip, type, criticality, status, policy_level, last_seen)"
                    " VALUES (?, ?, ?, ?, ?, 'ACTIVE', 0, ?)",
                    (device["id"], device["name"], device["ip"], device["type"],
                     device["criticality"], utc_now()),
                )
        conn.commit()


def query_all(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
    return dict(row) if row else None


def execute(sql: str, params: Iterable[Any] = ()) -> None:
    with connect() as conn:
        conn.execute(sql, tuple(params))
        conn.commit()


def insert(table: str, values: dict[str, Any]) -> dict[str, Any]:
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    with connect() as conn:
        conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values())
        )
        conn.commit()
    return values


def update(table: str, row_id: str, values: dict[str, Any]) -> None:
    assignments = ", ".join(f"{column} = ?" for column in values)
    with connect() as conn:
        conn.execute(
            f"UPDATE {table} SET {assignments} WHERE id = ?", (*values.values(), row_id)
        )
        conn.commit()


def as_json(value: Any) -> str:
    return json.dumps(value, default=str, allow_nan=False)


def parse_json(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback if fallback is not None else {}
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return fallback if fallback is not None else {}
