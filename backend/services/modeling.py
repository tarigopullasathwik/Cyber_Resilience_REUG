"""Model training, evaluation and persistence.

Every metric written to the database is computed from the held-out test split of
the selected preprocessing run. No metric is seeded, hardcoded or estimated for
display. Training happens in a background job and reports real progress.
"""

from __future__ import annotations

import math
import time
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import psutil
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.neural_network import MLPRegressor
from sklearn.svm import OneClassSVM
from sklearn.tree import DecisionTreeClassifier

from .. import db, settings
from ..jobs import Job
from . import preprocessing

MODEL_SPECS: dict[str, dict[str, Any]] = {
    "random_forest": {
        "label": "Random Forest", "family": "supervised", "available": True,
        "description": "Ensemble of decision trees; robust tabular baseline with feature importance.",
    },
    "xgboost": {
        "label": "XGBoost", "family": "supervised", "available": False,
        "description": "Gradient-boosted trees; strong tabular performance when the package is installed.",
    },
    "decision_tree": {
        "label": "Decision Tree", "family": "supervised", "available": True,
        "description": "Interpretable single tree; useful as an explainable baseline.",
    },
    "logistic_regression": {
        "label": "Logistic Regression", "family": "supervised", "available": True,
        "description": "Linear probabilistic baseline after the fitted preprocessing pipeline.",
    },
    "isolation_forest": {
        "label": "Isolation Forest", "family": "anomaly", "available": True,
        "description": "Unsupervised anomaly detector trained on benign traffic only.",
    },
    "one_class_svm": {
        "label": "One-Class SVM", "family": "anomaly", "available": True,
        "description": "Boundary-based novelty detector; capped sample size for tractability.",
    },
    "autoencoder": {
        "label": "Autoencoder (MLP reconstruction)", "family": "anomaly", "available": True,
        "description": "Reconstruction-error detector trained on benign traffic only.",
    },
}


def _xgboost_available() -> bool:
    try:
        import xgboost  # noqa: F401

        return True
    except ImportError:
        return False


MODEL_SPECS["xgboost"]["available"] = _xgboost_available()


class AutoencoderDetector:
    """Small dense autoencoder implemented with sklearn's MLPRegressor.

    The network is trained to reconstruct benign feature vectors; the mean
    squared reconstruction error is the anomaly score. This is a genuine
    reconstruction model, not a classifier.
    """

    def __init__(self, hidden: int = 32, max_iter: int = 160, random_state: int = 42) -> None:
        self.hidden = hidden
        self.max_iter = max_iter
        self.random_state = random_state
        self.model: MLPRegressor | None = None
        self.n_features = 0
        self.baseline_median = 0.0
        self.baseline_scale = 1.0

    def fit(self, features: np.ndarray) -> "AutoencoderDetector":
        n_features = features.shape[1]
        self.n_features = n_features
        hidden = max(8, min(int(self.hidden), max(8, n_features * 2)))
        self.model = MLPRegressor(
            hidden_layer_sizes=(hidden, max(4, hidden // 2), hidden),
            activation="relu",
            solver="adam",
            alpha=1e-4,
            batch_size=min(256, max(16, len(features) // 10)),
            learning_rate_init=1e-3,
            max_iter=int(self.max_iter),
            early_stopping=len(features) > 500,
            n_iter_no_change=12,
            random_state=self.random_state,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.model.fit(features, features)
        errors = self.reconstruction_error(features)
        self.baseline_median = float(np.median(errors))
        mad = float(np.median(np.abs(errors - self.baseline_median))) * 1.4826
        self.baseline_scale = max(mad, 1e-6)
        return self

    def reconstruction_error(self, features: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Autoencoder is not fitted.")
        reconstructed = self.model.predict(features)
        return np.mean((reconstructed - features) ** 2, axis=1)

    def score(self, features: np.ndarray) -> np.ndarray:
        return (self.reconstruction_error(features) - self.baseline_median) / self.baseline_scale


def build_model(
    model_name: str,
    params: dict[str, Any],
    random_state: int,
    class_balance: float = 1.0,
) -> Any:
    if model_name not in MODEL_SPECS:
        raise ValueError(f"Unknown model '{model_name}'.")
    if model_name == "xgboost" and not _xgboost_available():
        raise ValueError(
            "XGBoost is not installed on the backend. Install the optional dependency "
            "'xgboost' or choose another model."
        )
    p = params or {}
    if model_name == "random_forest":
        return RandomForestClassifier(
            n_estimators=int(p.get("n_estimators", 200)),
            max_depth=int(p["max_depth"]) if p.get("max_depth") else None,
            min_samples_leaf=int(p.get("min_samples_leaf", 1)),
            class_weight=p.get("class_weight", "balanced_subsample"),
            n_jobs=-1,
            random_state=random_state,
        )
    if model_name == "xgboost":
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=int(p.get("n_estimators", 200)),
            max_depth=int(p.get("max_depth", 5)),
            learning_rate=float(p.get("learning_rate", 0.1)),
            subsample=float(p.get("subsample", 0.9)),
            colsample_bytree=float(p.get("colsample_bytree", 0.9)),
            scale_pos_weight=float(p.get("scale_pos_weight", max(class_balance, 1.0))),
            tree_method="hist",
            n_jobs=2,
            random_state=random_state,
            eval_metric="logloss",
        )
    if model_name == "decision_tree":
        return DecisionTreeClassifier(
            max_depth=int(p["max_depth"]) if p.get("max_depth") else None,
            min_samples_leaf=int(p.get("min_samples_leaf", 1)),
            class_weight=p.get("class_weight", "balanced"),
            random_state=random_state,
        )
    if model_name == "logistic_regression":
        return LogisticRegression(
            C=float(p.get("C", 1.0)),
            max_iter=int(p.get("max_iter", 1000)),
            class_weight=p.get("class_weight", "balanced"),
            solver="lbfgs",
            random_state=random_state,
        )
    if model_name == "isolation_forest":
        return IsolationForest(
            n_estimators=int(p.get("n_estimators", 150)),
            max_samples=p.get("max_samples", "auto"),
            contamination="auto",
            random_state=random_state,
            n_jobs=-1,
        )
    if model_name == "one_class_svm":
        return OneClassSVM(
            kernel="rbf",
            gamma=p.get("gamma", "scale"),
            nu=float(p.get("nu", 0.05)),
        )
    if model_name == "autoencoder":
        return AutoencoderDetector(
            hidden=int(p.get("hidden", 32)),
            max_iter=int(p.get("max_iter", 160)),
            random_state=random_state,
        )
    raise ValueError(f"Unsupported model '{model_name}'.")


def _raw_scores(model: Any, features: np.ndarray) -> np.ndarray:
    if isinstance(model, AutoencoderDetector):
        return model.score(features)
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(features))[:, 1]
    if hasattr(model, "decision_function"):
        return -np.asarray(model.decision_function(features))
    return np.asarray(model.predict(features), dtype=float)


def normalize_scores(raw: np.ndarray, low: float, high: float) -> np.ndarray:
    if not math.isfinite(high) or high <= low:
        high = low + 1.0
    return np.clip((np.asarray(raw, dtype=float) - low) / (high - low), 0.0, 1.0)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _thin_curve(*arrays: np.ndarray, max_points: int = 140) -> list[np.ndarray]:
    length = len(arrays[0]) if arrays else 0
    if length <= max_points:
        return [np.asarray(array) for array in arrays]
    indices = np.linspace(0, length - 1, max_points).astype(int)
    return [np.asarray(array)[indices] for array in arrays]


def _curve_payload(y_true: np.ndarray, scores: np.ndarray) -> dict[str, Any]:
    payload: dict[str, Any] = {"roc": [], "pr": []}
    if len(np.unique(y_true)) < 2:
        payload["roc_auc"] = None
        payload["pr_auc"] = None
        return payload
    try:
        fpr, tpr, _ = roc_curve(y_true, scores)
        fpr, tpr = _thin_curve(fpr, tpr)
        payload["roc"] = [
            {"fpr": _finite(a), "tpr": _finite(b)} for a, b in zip(fpr, tpr)
        ]
        payload["roc_auc"] = _finite(roc_auc_score(y_true, scores))
    except ValueError:
        payload["roc_auc"] = None
    try:
        precision, recall, _ = precision_recall_curve(y_true, scores)
        recall, precision = _thin_curve(recall, precision)
        payload["pr"] = [
            {"recall": _finite(a), "precision": _finite(b)} for a, b in zip(recall, precision)
        ]
        payload["pr_auc"] = _finite(average_precision_score(y_true, scores))
    except ValueError:
        payload["pr_auc"] = None
    return payload


def _evaluate(
    y_true: np.ndarray,
    scores: np.ndarray,
    threshold: float,
    original_labels: np.ndarray,
) -> dict[str, Any]:
    predictions = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, predictions, labels=[0, 1]).ravel()
    metrics = {
        "accuracy": _finite(accuracy_score(y_true, predictions)),
        "precision": _finite(precision_score(y_true, predictions, zero_division=0)),
        "recall": _finite(recall_score(y_true, predictions, zero_division=0)),
        "f1": _finite(
            2 * precision_score(y_true, predictions, zero_division=0)
            * recall_score(y_true, predictions, zero_division=0)
            / max(precision_score(y_true, predictions, zero_division=0)
                  + recall_score(y_true, predictions, zero_division=0), 1e-12)
        ),
        "false_positive_rate": _finite(fp / (fp + tn)) if (fp + tn) else None,
        "false_negative_rate": _finite(fn / (fn + tp)) if (fn + tp) else None,
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "n_test": int(len(y_true)),
        "predicted_positive": int(predictions.sum()),
    }
    curves = _curve_payload(y_true, scores)
    metrics["roc_auc"] = curves.pop("roc_auc", None)
    metrics["pr_auc"] = curves.pop("pr_auc", None)

    per_class = []
    for label, name in ((0, "benign"), (1, "malicious")):
        mask = y_true == label
        support = int(mask.sum())
        detected = int(predictions[mask].sum())
        per_class.append(
            {
                "class": name,
                "support": support,
                "predicted_positive": detected,
                "recall": _finite(detected / support) if support else None,
                "mean_score": _finite(scores[mask].mean()) if support else None,
            }
        )

    per_family = []
    attack_mask = y_true == 1
    for family in sorted(set(original_labels[attack_mask].tolist())):
        mask = attack_mask & (original_labels == family)
        support = int(mask.sum())
        detected = int(predictions[mask].sum())
        per_family.append(
            {
                "family": str(family),
                "support": support,
                "detected": detected,
                "recall": _finite(detected / support) if support else None,
                "mean_score": _finite(scores[mask].mean()) if support else None,
            }
        )
    return {"metrics": metrics, "curves": curves, "per_class": per_class, "per_family": per_family}


def _feature_importance(model: Any, feature_names: list[str]) -> list[dict[str, Any]]:
    values = None
    if hasattr(model, "feature_importances_"):
        values = np.asarray(model.feature_importances_, dtype=float)
    elif hasattr(model, "coef_"):
        coef = np.asarray(model.coef_)
        values = np.abs(coef[0] if coef.ndim > 1 else coef)
    if values is None or len(values) != len(feature_names):
        return []
    order = np.argsort(values)[::-1][:25]
    return [
        {"feature": feature_names[index], "importance": _finite(values[index])}
        for index in order
    ]


def _measure_latency(score_fn: Any, features: np.ndarray, limit: int = 120) -> dict[str, Any]:
    probe = features[: min(limit, len(features))]
    if len(probe) == 0:
        return {"latency_mean_ms": None, "latency_p95_ms": None, "throughput_per_sec": None,
                "latency_samples": 0}
    for row in probe[: min(8, len(probe))]:
        score_fn(row.reshape(1, -1))
    timings = []
    for row in probe:
        start = time.perf_counter()
        score_fn(row.reshape(1, -1))
        timings.append((time.perf_counter() - start) * 1000.0)
    batch_start = time.perf_counter()
    score_fn(probe)
    batch_elapsed = max(time.perf_counter() - batch_start, 1e-9)
    return {
        "latency_mean_ms": round(float(np.mean(timings)), 4),
        "latency_p95_ms": round(float(np.percentile(timings, 95)), 4),
        "throughput_per_sec": round(float(len(probe) / batch_elapsed), 2),
        "latency_samples": int(len(timings)),
        "batch_size": int(len(probe)),
    }


def create_experiment(
    kind: str,
    name: str,
    model_name: str,
    dataset_id: str | None,
    preprocess_id: str | None,
    params: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "id": db.new_id("exp_"),
        "name": name,
        "kind": kind,
        "dataset_id": dataset_id,
        "preprocess_id": preprocess_id,
        "model_name": model_name,
        "params_json": db.as_json(params),
        "metrics_json": "{}",
        "curves_json": "{}",
        "confusion_json": "{}",
        "per_class_json": "[]",
        "per_family_json": "[]",
        "feature_importance_json": "[]",
        "artifact_path": None,
        "preprocessor_path": None,
        "predictions_path": None,
        "status": "queued",
        "progress": 0.0,
        "message": "Queued",
        "config_json": db.as_json(config or {}),
        "created_at": db.utc_now(),
        "completed_at": None,
    }
    db.insert("experiments", record)
    return experiment_record(record)


def experiment_record(row: dict[str, Any], include_curves: bool = True) -> dict[str, Any]:
    record = {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "dataset_id": row["dataset_id"],
        "preprocess_id": row["preprocess_id"],
        "model_name": row["model_name"],
        "params": db.parse_json(row.get("params_json"), {}),
        "metrics": db.parse_json(row.get("metrics_json"), {}),
        "confusion": db.parse_json(row.get("confusion_json"), {}),
        "per_class": db.parse_json(row.get("per_class_json"), []),
        "per_family": db.parse_json(row.get("per_family_json"), []),
        "feature_importance": db.parse_json(row.get("feature_importance_json"), []),
        "status": row["status"],
        "progress": row.get("progress", 0),
        "message": row.get("message"),
        "config": db.parse_json(row.get("config_json"), {}),
        "created_at": row["created_at"],
        "completed_at": row.get("completed_at"),
        "artifact_saved": bool(row.get("artifact_path") and Path(row["artifact_path"]).exists()),
        "predictions_available": bool(
            row.get("predictions_path") and Path(row["predictions_path"]).exists()
        ),
    }
    if include_curves:
        record["curves"] = db.parse_json(row.get("curves_json"), {})
    return record


def list_experiments(kind: str | None = None) -> list[dict[str, Any]]:
    if kind:
        rows = db.query_all(
            "SELECT * FROM experiments WHERE kind = ? ORDER BY created_at DESC", (kind,)
        )
    else:
        rows = db.query_all("SELECT * FROM experiments ORDER BY created_at DESC")
    return [experiment_record(row) for row in rows]


def get_experiment(experiment_id: str, include_curves: bool = True) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
    if not row:
        raise ValueError("Experiment not found.")
    return experiment_record(row, include_curves=include_curves)


def get_experiment_row(experiment_id: str) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
    if not row:
        raise ValueError("Experiment not found.")
    return row


def run_experiment(experiment_id: str, job: Job) -> dict[str, Any]:
    row = get_experiment_row(experiment_id)
    model_name = row["model_name"]
    spec = MODEL_SPECS.get(model_name)
    if not spec:
        raise ValueError(f"Unknown model '{model_name}'.")
    if not row["preprocess_id"]:
        raise ValueError("A preprocessing run is required before training a model.")
    run_row = preprocessing.get_run_row(row["preprocess_id"])
    splits = preprocessing.load_splits(run_row)
    artifact_meta = preprocessing.load_preprocessor(run_row)
    feature_names = db.parse_json(run_row["feature_names_json"], [])
    params = db.parse_json(row["params_json"], {})
    random_state = int(params.get("random_state", 42))
    supervised = spec["family"] == "supervised"

    db.update("experiments", experiment_id, {"status": "running", "progress": 0.04,
                                             "message": "Loading preprocessed splits"})
    job.update(0.04, "Loading preprocessed splits")

    all_features = feature_names or [
        column for column in splits["train"].columns if not column.startswith("__target")
    ]
    train = splits["train"]
    val = splits["val"]
    test = splits["test"]
    if supervised:
        X_train = train[all_features].to_numpy(dtype=np.float32)
        X_val = val[all_features].to_numpy(dtype=np.float32)
        X_val_all = X_val
        X_test = test[all_features].to_numpy(dtype=np.float32)
        y_train = train["__target_binary"].to_numpy(dtype=int)
        y_val = val["__target_binary"].to_numpy(dtype=int)
        y_test = test["__target_binary"].to_numpy(dtype=int)
        family_test = test["__target_original"].astype(str).to_numpy()
        family_val = val["__target_original"].astype(str).to_numpy()
    else:
        X_train_all = train[all_features].to_numpy(dtype=np.float32)
        y_train_all = train["__target_binary"].to_numpy(dtype=int)
        X_train = X_train_all[y_train_all == 0]
        X_val_all = val[all_features].to_numpy(dtype=np.float32)
        y_val_all = val["__target_binary"].to_numpy(dtype=int)
        X_test = test[all_features].to_numpy(dtype=np.float32)
        y_test = test["__target_binary"].to_numpy(dtype=int)
        family_test = test["__target_original"].astype(str).to_numpy()
        family_val = val["__target_original"].astype(str).to_numpy()

    if len(X_train) == 0 or len(X_test) == 0:
        raise ValueError("The preprocessing split is empty. Re-run preprocessing with more rows.")
    balanced = float((y_train == 0).sum() / max((y_train == 1).sum(), 1)) if supervised else 1.0

    process = psutil.Process()
    cpu_before = process.cpu_times()
    wall_start = time.perf_counter()
    job.update(0.12, f"Fitting {spec['label']} on {len(X_train):,} training rows")

    model = build_model(model_name, params, random_state, class_balance=balanced)
    if model_name == "one_class_svm" and len(X_train) > 8000:
        rng = np.random.default_rng(random_state)
        sample = rng.choice(len(X_train), size=8000, replace=False)
        X_fit = X_train[sample]
        job.update(0.2, "Fitting One-Class SVM on a 8,000-row benign sample")
    elif model_name == "autoencoder" and len(X_train) > 20000:
        rng = np.random.default_rng(random_state)
        sample = rng.choice(len(X_train), size=20000, replace=False)
        X_fit = X_train[sample]
        job.update(0.2, "Fitting autoencoder on a 20,000-row benign sample")
    else:
        X_fit = X_train

    if supervised:
        model.fit(X_train, y_train)
        threshold = 0.5
        score_kind = "probability"
        lo, hi = 0.0, 1.0
        job.update(0.55, "Scoring validation and test splits")
    else:
        if len(X_fit) < 20:
            raise ValueError("Not enough benign training rows for an anomaly detector.")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(X_fit)
        benign_val_mask = y_val_all == 0
        ref = X_val_all[benign_val_mask] if benign_val_mask.sum() >= 20 else X_fit
        raw_ref = _raw_scores(model, ref)
        lo = float(np.percentile(raw_ref, 1))
        hi = float(np.percentile(raw_ref, 99.5))
        normalized_ref = normalize_scores(raw_ref, lo, hi)
        threshold = float(np.quantile(normalized_ref, float(params.get("threshold_quantile", 0.99))))
        threshold = max(0.02, min(0.98, threshold))
        score_kind = "anomaly"
        job.update(0.55, "Calibrating the anomaly threshold on benign validation scores")

    wall_seconds = max(time.perf_counter() - wall_start, 1e-9)
    cpu_after = process.cpu_times()
    cpu_seconds = (cpu_after.user + cpu_after.system) - (cpu_before.user + cpu_before.system)
    rss_mb = process.memory_info().rss / (1024 * 1024)

    def score_features(features: np.ndarray) -> np.ndarray:
        raw = _raw_scores(model, features)
        return raw if supervised else normalize_scores(raw, lo, hi)

    job.update(0.68, "Evaluating on the held-out test split")
    scores_val = score_features(X_val_all)
    scores_test = score_features(X_test)
    evaluation = _evaluate(y_test, scores_test, threshold, family_test)

    job.update(0.78, "Measuring inference latency")
    latency = _measure_latency(score_features, X_test)

    experiment_dir = settings.ARTIFACT_DIR / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = settings.MODEL_DIR / f"{experiment_id}.joblib"
    joblib.dump(
        {
            "model": model,
            "model_name": model_name,
            "family": spec["family"],
            "feature_names": all_features,
            "threshold": threshold,
            "score_kind": score_kind,
            "norm_low": lo,
            "norm_high": hi,
            "preprocessor_path": run_row["preprocessor_path"],
            "preprocess_id": run_row["id"],
            "dataset_id": run_row["dataset_id"],
            "params": params,
        },
        artifact_path,
    )
    model_size = artifact_path.stat().st_size

    predictions = pd.DataFrame(
        {
            "row_index": np.arange(len(y_test)),
            "score": scores_test,
            "score_supervised": scores_test if supervised else np.full(len(y_test), np.nan),
            "score_anomaly": np.nan if supervised else scores_test,
            "predicted": (scores_test >= threshold).astype(int),
            "y_binary": y_test,
            "y_family": family_test,
        }
    )
    predictions_path = experiment_dir / "test_predictions.parquet"
    predictions.to_parquet(predictions_path, index=False)

    metrics = evaluation["metrics"]
    metrics.update(
        {
            "model": model_name,
            "model_label": spec["label"],
            "model_family": spec["family"],
            "threshold": threshold,
            "score_kind": score_kind,
            "training_seconds": round(wall_seconds, 3),
            "training_cpu_seconds": round(float(cpu_seconds), 3),
            "host_cpu_percent_during_training": _finite(100.0 * cpu_seconds / wall_seconds),
            "host_memory_rss_mb": round(rss_mb, 1),
            "model_size_bytes": int(model_size),
            "model_size_mb": round(model_size / (1024 * 1024), 4),
            "inference_latency_ms_mean": latency["latency_mean_ms"],
            "inference_latency_ms_p95": latency["latency_p95_ms"],
            "throughput_records_per_sec": latency["throughput_per_sec"],
            "latency_samples": latency["latency_samples"],
            "n_features": len(all_features),
            "n_train": int(len(X_train)),
            "n_val": int(len(X_val_all)),
            "val_predicted_positive": int((scores_val >= threshold).sum()),
            "dataset_id": run_row["dataset_id"],
            "preprocess_id": run_row["id"],
            "feature_names": all_features[:400],
        }
    )
    curves = evaluation["curves"]
    curves["score_distribution"] = {
        "benign": [float(value) for value in scores_test[y_test == 0][:3000]],
        "malicious": [float(value) for value in scores_test[y_test == 1][:3000]],
    }

    db.update(
        "experiments",
        experiment_id,
        {
            "status": "completed",
            "progress": 1.0,
            "message": "Training and evaluation complete",
            "metrics_json": db.as_json(metrics),
            "curves_json": db.as_json(curves),
            "confusion_json": db.as_json(metrics),
            "per_class_json": db.as_json(evaluation["per_class"]),
            "per_family_json": db.as_json(evaluation["per_family"]),
            "feature_importance_json": db.as_json(_feature_importance(model, all_features)),
            "artifact_path": str(artifact_path),
            "preprocessor_path": run_row["preprocessor_path"],
            "predictions_path": str(predictions_path),
            "completed_at": db.utc_now(),
        },
    )
    job.update(1.0, "Model trained and evaluated on the unseen test split")
    return get_experiment(experiment_id)


def load_artifact(experiment_id: str) -> dict[str, Any]:
    row = get_experiment_row(experiment_id)
    path = row.get("artifact_path")
    if not path or not Path(path).exists():
        raise ValueError("This experiment has no saved model artifact.")
    return joblib.load(path)


def predict_frame(experiment_id: str, frame: pd.DataFrame) -> dict[str, Any]:
    artifact = load_artifact(experiment_id)
    preprocessor_path = Path(artifact["preprocessor_path"])
    if not preprocessor_path.exists():
        raise ValueError("The preprocessing artifact for this model is missing.")
    bundle = joblib.load(preprocessor_path)
    pipeline = bundle["pipeline"]
    required = bundle["feature_columns"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(
            "Uploaded data is missing required columns: " + ", ".join(missing[:8])
        )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        matrix = pipeline.transform(frame[required])
    if hasattr(matrix, "toarray"):
        matrix = matrix.toarray()
    features = np.asarray(matrix, dtype=np.float32)
    model = artifact["model"]
    raw = _raw_scores(model, features)
    scores = raw if artifact["score_kind"] == "probability" else normalize_scores(
        raw, artifact["norm_low"], artifact["norm_high"]
    )
    threshold = float(artifact["threshold"])
    predictions = (scores >= threshold).astype(int)
    records = []
    for index in range(min(len(predictions), 500)):
        records.append(
            {
                "row": int(index),
                "score": round(float(scores[index]), 6),
                "predicted": int(predictions[index]),
                "label": "malicious" if predictions[index] else "benign",
                "threshold": threshold,
            }
        )
    return {
        "experiment_id": experiment_id,
        "model_name": artifact["model_name"],
        "threshold": threshold,
        "scored_rows": int(len(predictions)),
        "flagged": int(predictions.sum()),
        "predictions": records,
    }
