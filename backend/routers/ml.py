"""API routes for preprocessing, model training, prediction and unknown attacks."""

from __future__ import annotations

import io
import shutil
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import db, jobs as job_registry, settings
from ..services import modeling, preprocessing, unknown

router = APIRouter(prefix="/api", tags=["ml"])


class PreprocessRequest(BaseModel):
    dataset_id: str
    target_column: str | None = None
    drop_columns: list[str] = Field(default_factory=list)
    benign_labels: list[str] | None = None
    remove_duplicates: bool = True
    handle_infinite: bool = True
    drop_identifiers: bool = True
    missing_strategy: Literal["median", "mean", "drop_rows"] = "median"
    scaling: Literal["standard", "minmax", "robust", "none"] = "standard"
    imbalance: Literal["class_weight", "oversample", "none"] = "class_weight"
    max_missing_fraction: float = Field(default=0.6, ge=0.0, le=1.0)
    max_onehot_categories: int = Field(default=24, ge=2, le=200)
    top_k: int = Field(default=0, ge=0, le=1000)
    test_size: float = Field(default=0.2, ge=0.05, le=0.5)
    val_size: float = Field(default=0.15, ge=0.05, le=0.4)
    random_state: int = 42
    max_rows: int = Field(default=250_000, ge=200, le=2_000_000)


class TrainRequest(BaseModel):
    preprocess_id: str
    dataset_id: str | None = None
    model_name: str = "random_forest"
    params: dict[str, Any] = Field(default_factory=dict)
    name: str | None = None


class UnknownRequest(BaseModel):
    preprocess_id: str
    dataset_id: str | None = None
    mode: Literal["holdout", "lofo"] = "holdout"
    holdout_families: list[str] = Field(default_factory=list)
    supervised_model: str = "random_forest"
    anomaly_model: str = "isolation_forest"
    n_estimators: int = Field(default=160, ge=20, le=600)
    anomaly_estimators: int = Field(default=120, ge=20, le=600)
    threshold_quantile: float = Field(default=0.99, ge=0.5, le=0.999)
    max_families: int = Field(default=5, ge=1, le=12)
    max_train_rows: int = Field(default=60_000, ge=500, le=500_000)
    name: str | None = None


@router.get("/preprocess/runs")
def list_runs(dataset_id: str | None = None) -> list[dict[str, Any]]:
    return preprocessing.list_runs(dataset_id)


@router.post("/preprocess/runs", status_code=202)
def start_preprocessing(body: PreprocessRequest) -> dict[str, Any]:
    config = body.model_dump()
    dataset_id = config.pop("dataset_id")
    job = job_registry.jobs.submit(
        "preprocessing",
        lambda active: preprocessing.run_preprocessing(dataset_id, config, active),
        meta={"dataset_id": dataset_id},
    )
    return {"job": job.as_dict(), "message": "Preprocessing started."}


@router.get("/preprocess/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return preprocessing.get_run(run_id)


@router.get("/preprocess/runs/{run_id}/families")
def families(run_id: str) -> dict[str, Any]:
    return unknown.available_families(run_id)


@router.get("/models")
def list_models() -> list[dict[str, Any]]:
    return [
        {"key": key, **spec, "params": _param_hints(key)}
        for key, spec in modeling.MODEL_SPECS.items()
    ]


def _param_hints(key: str) -> dict[str, Any]:
    if key == "random_forest":
        return {"n_estimators": 200, "max_depth": None, "min_samples_leaf": 1}
    if key == "xgboost":
        return {"n_estimators": 200, "max_depth": 5, "learning_rate": 0.1}
    if key == "decision_tree":
        return {"max_depth": 12, "min_samples_leaf": 2}
    if key == "logistic_regression":
        return {"C": 1.0, "max_iter": 1000}
    if key == "isolation_forest":
        return {"n_estimators": 150}
    if key == "one_class_svm":
        return {"nu": 0.05}
    if key == "autoencoder":
        return {"hidden": 32, "max_iter": 160}
    return {}


@router.get("/experiments")
def list_experiments(kind: str | None = None) -> list[dict[str, Any]]:
    return modeling.list_experiments(kind)


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str) -> dict[str, Any]:
    return modeling.get_experiment(experiment_id)


@router.delete("/experiments/{experiment_id}", status_code=204)
def delete_experiment(experiment_id: str) -> None:
    row = modeling.get_experiment_row(experiment_id)
    for key in ("artifact_path", "predictions_path"):
        if row.get(key):
            Path(row[key]).unlink(missing_ok=True)
    shutil.rmtree(settings.ARTIFACT_DIR / experiment_id, ignore_errors=True)
    db.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))


@router.post("/experiments", status_code=202)
def train_model(body: TrainRequest) -> dict[str, Any]:
    spec = modeling.MODEL_SPECS.get(body.model_name)
    if not spec:
        raise HTTPException(status_code=400, detail=f"Unknown model '{body.model_name}'.")
    if not spec["available"]:
        raise HTTPException(
            status_code=400,
            detail=f"{spec['label']} is not installed on this backend. Choose another model.",
        )
    run = preprocessing.get_run(body.preprocess_id)
    if body.dataset_id and run["dataset_id"] != body.dataset_id:
        raise HTTPException(status_code=400, detail="The preprocessing run does not belong to this dataset.")
    name = body.name or f"{spec['label']} · {run['name']}"
    experiment = modeling.create_experiment(
        kind="supervised" if spec["family"] == "supervised" else "anomaly",
        name=name,
        model_name=body.model_name,
        dataset_id=run["dataset_id"],
        preprocess_id=body.preprocess_id,
        params=body.params,
        config={"threshold": "0.5" if spec["family"] == "supervised" else "quantile"},
    )
    job = job_registry.jobs.submit(
        "training",
        lambda active: _run_training_job(experiment["id"], active),
        meta={"experiment_id": experiment["id"]},
    )
    return {"experiment": experiment, "job": job.as_dict(), "message": "Training started."}


@router.post("/unknown/experiments", status_code=202)
def start_unknown(body: UnknownRequest) -> dict[str, Any]:
    run = preprocessing.get_run(body.preprocess_id)
    params = body.model_dump()
    params.pop("preprocess_id", None)
    params.pop("dataset_id", None)
    name = body.name or f"Unknown-attack study · {run['name']}"
    experiment = modeling.create_experiment(
        kind="unknown",
        name=name,
        model_name=f"{body.supervised_model}+{body.anomaly_model}",
        dataset_id=run["dataset_id"],
        preprocess_id=body.preprocess_id,
        params=params,
        config={"mode": body.mode, "heldout": body.holdout_families},
    )
    job = job_registry.jobs.submit(
        "unknown_attack",
        lambda active: _run_unknown_job(experiment["id"], active),
        meta={"experiment_id": experiment["id"]},
    )
    return {"experiment": experiment, "job": job.as_dict(), "message": "Unknown-attack study started."}


def _mark_failed(experiment_id: str, message: str) -> None:
    db.update(
        "experiments",
        experiment_id,
        {"status": "failed", "message": message, "progress": 0.0},
    )


def _run_training_job(experiment_id: str, active) -> Any:
    try:
        return modeling.run_experiment(experiment_id, active)
    except Exception as exc:
        _mark_failed(experiment_id, f"Training failed: {exc}")
        raise


def _run_unknown_job(experiment_id: str, active) -> Any:
    try:
        return unknown.run_unknown(experiment_id, active)
    except Exception as exc:
        _mark_failed(experiment_id, f"Unknown-attack study failed: {exc}")
        raise


@router.post("/experiments/{experiment_id}/predict")
def predict(experiment_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith((".csv", ".parquet")):
        raise HTTPException(status_code=415, detail="Upload a CSV or Parquet file of raw feature rows.")
    payload = file.file.read()
    try:
        if file.filename.lower().endswith(".parquet"):
            frame = pd.read_parquet(io.BytesIO(payload))
        else:
            frame = pd.read_csv(io.BytesIO(payload))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not parse the uploaded file: {exc}") from exc
    if frame.empty:
        raise HTTPException(status_code=400, detail="The uploaded file has no rows.")
    try:
        return modeling.predict_frame(experiment_id, frame)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
