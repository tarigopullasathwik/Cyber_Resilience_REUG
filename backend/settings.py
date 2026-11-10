"""Runtime configuration for the EDGEGUARD AI backend.

All mutable state (datasets, fitted preprocessors, trained models, reports and
the SQLite database) lives under ``EDGEGUARD_DATA_DIR`` which defaults to
``data/edgeguard``. Kaggle credentials are only ever read from environment
variables or the standard Kaggle config file; they are never returned by an API.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DATA_DIR: Path = Path(os.environ.get("EDGEGUARD_DATA_DIR", PROJECT_ROOT / "data" / "edgeguard"))
DB_PATH: Path = Path(os.environ.get("EDGEGUARD_DB_PATH", DATA_DIR / "edgeguard.sqlite3"))
DATASET_DIR: Path = DATA_DIR / "datasets"
ARTIFACT_DIR: Path = DATA_DIR / "artifacts"
MODEL_DIR: Path = DATA_DIR / "models"
REPORT_DIR: Path = DATA_DIR / "reports"
KAGGLE_DIR: Path = DATA_DIR / "kaggle"
EDGE_BUDGET_PATH: Path = DATA_DIR / "edge_budget.json"

for _directory in (DATA_DIR, DATASET_DIR, ARTIFACT_DIR, MODEL_DIR, REPORT_DIR, KAGGLE_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES: int = int(float(os.environ.get("EDGEGUARD_MAX_UPLOAD_MB", "512")) * 1024 * 1024)
MAX_KAGGLE_BYTES: int = int(float(os.environ.get("EDGEGUARD_MAX_KAGGLE_MB", "2048")) * 1024 * 1024)
SYNC_JOBS: bool = _as_bool(os.environ.get("EDGEGUARD_SYNC_JOBS"), False)

CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.environ.get(
        "EDGEGUARD_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if origin.strip()
]

RESEARCH_TITLE = (
    "Design and Development of an Adaptive Edge Cyber-Resilience Mechanism for "
    "Real-Time Detection and Autonomous Containment of Unknown Attacks in "
    "Resource-Constrained IoT Networks"
)

SCOPE_NOTE = (
    "Research prototype. Network devices, containment actions and edge resource budgets "
    "are simulated. Host CPU, memory and latency figures are measured on this machine. "
    "No real network is scanned or blocked."
)
