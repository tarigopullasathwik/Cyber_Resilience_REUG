"""Leakage-safe preprocessing engine.

Order of operations (deliberate):

1. load the dataset, drop rows without a target label
2. derive a binary benign/malicious target and keep the original family label
3. remove duplicate rows
4. split the data first (train / validation / test, stratified)
5. fit imputers, encoders, the scaler and feature selection on the training split
   only, then apply the fitted transformation to validation and test
6. oversample the training split only, if requested

The fitted pipeline is persisted so training, prediction and containment
verification all use the exact transformation that was fitted on train.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.feature_selection import VarianceThreshold, f_classif
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder, RobustScaler, StandardScaler

from .. import db, settings
from ..jobs import Job
from . import datasets

BENIGN_LABELS = {
    "benign", "normal", "normal traffic", "benign traffic", "legitimate", "legit",
    "no attack", "no_attack", "none", "0", "0.0", "false", "clean",
}
ID_COLUMN = re.compile(
    r"(^id$|_id$|^id_|flow.?id|session.?id|src.?ip|dst.?ip|source.?ip|destination.?ip|"
    r"^source$|^destination$|^src$|^dst$|timestamp|^time$|^date$|unnamed:\s*0|^index$|"
    r"^frame$|^mac$|mac.?address|^row$)",
    re.I,
)


class PreprocessError(ValueError):
    pass


class TopKFeatures(TransformerMixin, BaseEstimator):
    """Univariate top-k selector that clamps k to the fitted feature count.

    SelectKBest raises when k exceeds the number of transformed columns, which can
    happen after variance filtering. This selector computes the same F-scores but
    resolves k at fit time, so a user requesting 50 features on a 40-feature matrix
    gets 40 instead of a failed job.
    """

    def __init__(self, k: int = 0) -> None:
        self.k = k

    def fit(self, features: Any, labels: Any = None) -> "TopKFeatures":
        matrix = np.asarray(features)
        self.n_features_in_ = matrix.shape[1]
        requested = int(self.k or 0)
        if requested <= 0 or requested >= matrix.shape[1]:
            self.support_ = np.ones(matrix.shape[1], dtype=bool)
            self.scores_ = np.ones(matrix.shape[1], dtype=float)
        else:
            scores, _ = f_classif(matrix, labels)
            scores = np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)
            chosen = np.argsort(scores)[::-1][:requested]
            self.support_ = np.zeros(matrix.shape[1], dtype=bool)
            self.support_[chosen] = True
            self.scores_ = scores
        return self

    def transform(self, features: Any) -> np.ndarray:
        return np.asarray(features)[:, self.support_]

    def get_support(self, indices: bool = False) -> Any:
        return np.where(self.support_)[0] if indices else self.support_


def _benign_labels(series: pd.Series, explicit: list[str] | None) -> list[str]:
    values = {str(value).strip() for value in series.dropna().unique()}
    lowered = {value.lower(): value for value in values}
    if explicit:
        chosen = []
        for label in explicit:
            match = lowered.get(str(label).strip().lower())
            if match is None:
                raise PreprocessError(f"Benign label '{label}' does not occur in the target column.")
            chosen.append(match)
        return chosen
    chosen = [value for key, value in lowered.items() if key in BENIGN_LABELS]
    if not chosen and values <= {"0", "1"}:
        chosen = [lowered["0"]]
    if not chosen:
        raise PreprocessError(
            "Could not identify a benign label. Select the target column that contains "
            "normal/benign traffic, or provide benign labels explicitly."
        )
    return chosen


def _feature_names(pipeline: Pipeline) -> list[str]:
    try:
        names = [str(name) for name in pipeline.named_steps["columns"].get_feature_names_out()]
    except Exception:  # noqa: BLE001
        return []
    if "variance" in pipeline.named_steps:
        mask = pipeline.named_steps["variance"].get_support()
        if len(mask) == len(names):
            names = [name for name, keep in zip(names, mask) if keep]
    if "select" in pipeline.named_steps:
        mask = pipeline.named_steps["select"].get_support()
        if len(mask) == len(names):
            names = [name for name, keep in zip(names, mask) if keep]
    return names


def _safe_frame(matrix: Any, names: list[str]) -> pd.DataFrame:
    if hasattr(matrix, "toarray"):
        matrix = matrix.toarray()
    frame = pd.DataFrame(np.asarray(matrix), columns=names)
    return frame.astype("float32")


def _build_pipeline(
    numeric: list[str],
    categorical: list[str],
    config: dict[str, Any],
    n_features: int,
) -> Pipeline:
    steps: list[tuple[str, Any]] = []
    transformers: list[tuple[str, Any, list[str]]] = []

    if numeric:
        missing = config.get("missing_strategy", "median")
        strategy = "median" if missing in {"median", "drop_rows"} else "mean"
        numeric_steps: list[tuple[str, Any]] = [
            ("imputer", SimpleImputer(strategy=strategy, keep_empty_features=True))
        ]
        scaling = config.get("scaling", "standard")
        if scaling == "standard":
            numeric_steps.append(("scale", StandardScaler()))
        elif scaling == "minmax":
            numeric_steps.append(("scale", MinMaxScaler()))
        elif scaling == "robust":
            numeric_steps.append(("scale", RobustScaler()))
        transformers.append(("num", Pipeline(numeric_steps), numeric))

    if categorical:
        max_categories = int(config.get("max_onehot_categories", 24))
        transformers.append(
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
                        (
                            "onehot",
                            OneHotEncoder(
                                handle_unknown="ignore",
                                sparse_output=False,
                                max_categories=max(2, max_categories),
                            ),
                        ),
                    ]
                ),
                categorical,
            )
        )

    columns = ColumnTransformer(transformers, remainder="drop", sparse_threshold=0.0)
    steps.append(("columns", columns))
    steps.append(("variance", VarianceThreshold(threshold=0.0)))
    top_k = int(config.get("top_k") or 0)
    if top_k > 0:
        steps.append(("select", TopKFeatures(k=top_k)))
    return Pipeline(steps)


def run_preprocessing(dataset_id: str, config: dict[str, Any], job: Job) -> dict[str, Any]:
    dataset = datasets.get_dataset(dataset_id)
    target_column = config.get("target_column") or dataset.get("target_column")
    if not target_column:
        raise PreprocessError(
            "This dataset has no target column selected. Choose the label column in Dataset Management first."
        )
    if target_column not in dataset["columns"]:
        raise PreprocessError(f"Target column '{target_column}' is not present in the dataset.")

    job.update(0.05, "Loading dataset")
    frame = datasets.read_frame(dataset_id)
    if target_column not in frame.columns:
        raise PreprocessError(f"Target column '{target_column}' is missing from the stored file.")

    before_missing = int(frame.isna().sum().sum())
    before_rows = int(len(frame))

    frame = frame[frame[target_column].notna()].copy()
    if frame.empty:
        raise PreprocessError("Every row has a missing target label.")

    y_original = frame[target_column].astype(str).str.strip()
    benign_labels = _benign_labels(y_original, config.get("benign_labels"))
    y_binary = (~y_original.str.lower().isin({label.lower() for label in benign_labels})).astype(int)
    if y_binary.nunique() < 2:
        raise PreprocessError(
            "The selected target column contains only one class after mapping benign labels. "
            "Choose a target column with both benign and attack records."
        )

    frame["__target_original"] = y_original.values
    frame["__target_binary"] = y_binary.values

    duplicate_count = 0
    if config.get("remove_duplicates", True):
        duplicates = frame.duplicated()
        duplicate_count = int(duplicates.sum())
        frame = frame[~duplicates]

    if config.get("handle_infinite", True):
        numeric_columns = frame.select_dtypes(include=[np.number]).columns
        if len(numeric_columns):
            frame[numeric_columns] = frame[numeric_columns].replace([np.inf, -np.inf], np.nan)

    # --- cap very large files (explicitly reported in the statistics) ---------- #
    max_rows = int(config.get("max_rows") or 250_000)
    sampled = False
    if max_rows and len(frame) > max_rows:
        warnings.filterwarnings("ignore", category=UserWarning)
        frame, _ = train_test_split(
            frame, train_size=max_rows, stratify=frame["__target_binary"],
            random_state=int(config.get("random_state", 42)),
        )
        sampled = True

    # --- choose candidate feature columns ------------------------------------- #
    excluded = {target_column, "__target_original", "__target_binary"}
    explicit_drop = {str(column) for column in config.get("drop_columns", [])}
    identifier_columns = []
    for column in frame.columns:
        if column in excluded or column in explicit_drop:
            continue
        if config.get("drop_identifiers", True) and (ID_COLUMN.search(str(column)) or ID_COLUMN.search(
            str(dataset["dtypes"].get(column, ""))
        )):
            identifier_columns.append(column)
    excluded |= set(identifier_columns) | explicit_drop

    candidate_columns = [column for column in frame.columns if column not in excluded]
    if not candidate_columns:
        raise PreprocessError("No usable feature columns remain after excluding identifiers and the target.")

    incomplete_rows = 0
    if config.get("missing_strategy") == "drop_rows":
        before_incomplete = int(len(frame))
        frame = frame.dropna(subset=candidate_columns).copy()
        incomplete_rows = before_incomplete - int(len(frame))
        if frame.empty:
            raise PreprocessError("Every row has a missing feature value after choosing drop-rows handling.")
        if frame["__target_binary"].nunique() < 2:
            raise PreprocessError("Dropping incomplete rows removed one of the target classes.")

    # --- split first, fit later ------------------------------------------------ #
    test_size = float(config.get("test_size", 0.2))
    val_size = float(config.get("val_size", 0.15))
    if not 0.05 <= test_size <= 0.5 or not 0.05 <= val_size <= 0.4:
        raise PreprocessError("test_size must be in [0.05, 0.5] and val_size in [0.05, 0.4].")
    if test_size + val_size >= 0.8:
        raise PreprocessError("test_size + val_size must leave at least 20% for training.")
    random_state = int(config.get("random_state", 42))
    y = frame["__target_binary"]
    train_frame, test_frame = train_test_split(
        frame, test_size=test_size, stratify=y, random_state=random_state
    )
    relative_val = val_size / (1.0 - test_size)
    train_frame, val_frame = train_test_split(
        train_frame, test_size=relative_val, stratify=train_frame["__target_binary"],
        random_state=random_state,
    )
    if train_frame["__target_binary"].nunique() < 2:
        raise PreprocessError("The training split contains only one class. Provide more attack/benign rows.")

    job.update(0.2, "Fitting preprocessing on the training split")
    missing_fraction_limit = float(config.get("max_missing_fraction", 0.6))
    missing_fraction = train_frame[candidate_columns].isna().mean()
    high_missing_columns = [column for column in candidate_columns if missing_fraction[column] > missing_fraction_limit]
    usable = [column for column in candidate_columns if column not in high_missing_columns]
    constant_columns = [column for column in usable if train_frame[column].nunique(dropna=False) <= 1]
    usable = [column for column in usable if column not in constant_columns]
    if not usable:
        raise PreprocessError("All candidate features were empty or constant on the training split.")

    numeric = [column for column in usable
               if pd.api.types.is_numeric_dtype(train_frame[column])]
    categorical = [column for column in usable if column not in numeric]

    n_features_guess = len(numeric) + len(categorical)
    pipeline = _build_pipeline(numeric, categorical, config, n_features_guess)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pipeline.fit(train_frame[usable], train_frame["__target_binary"])

    feature_names = _feature_names(pipeline)
    if not feature_names:
        transformed_probe = pipeline.transform(train_frame[usable].head(2))
        feature_names = [f"feature_{index}" for index in range(transformed_probe.shape[1])]

    def transform(part: pd.DataFrame) -> pd.DataFrame:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            matrix = pipeline.transform(part[usable])
        result = _safe_frame(matrix, feature_names)
        result["__target_binary"] = part["__target_binary"].to_numpy(dtype=int)
        result["__target_original"] = part["__target_original"].astype(str).to_numpy()
        return result

    train_ready = transform(train_frame)
    val_ready = transform(val_frame)
    test_ready = transform(test_frame)

    # --- imbalance handling: training split only ------------------------------- #
    imbalance = config.get("imbalance", "class_weight")
    oversampled = False
    if imbalance == "oversample":
        counts = train_ready["__target_binary"].value_counts()
        target_count = int(counts.max())
        rng = np.random.default_rng(random_state)
        pieces = [train_ready]
        for label, count in counts.items():
            if count < target_count:
                extra = train_ready[train_ready["__target_binary"] == label].sample(
                    n=target_count - int(count), replace=True, random_state=int(rng.integers(1e9))
                )
                pieces.append(extra)
        train_ready = pd.concat(pieces).sample(frac=1.0, random_state=random_state).reset_index(drop=True)
        oversampled = True

    artifact_dir = settings.ARTIFACT_DIR / db.new_id("pp_")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    train_path = artifact_dir / "train.parquet"
    val_path = artifact_dir / "val.parquet"
    test_path = artifact_dir / "test.parquet"
    raw_test_path = artifact_dir / "test_raw.parquet"
    train_ready.to_parquet(train_path, index=False)
    val_ready.to_parquet(val_path, index=False)
    test_ready.to_parquet(test_path, index=False)
    raw_test = test_frame[usable + ["__target_binary", "__target_original"]].copy()
    raw_test.to_parquet(raw_test_path, index=False)

    preprocessor_path = artifact_dir / "preprocessor.joblib"
    joblib.dump(
        {
            "pipeline": pipeline,
            "feature_columns": usable,
            "numeric_columns": numeric,
            "categorical_columns": categorical,
            "feature_names": feature_names,
            "target_column": target_column,
            "benign_labels": benign_labels,
        },
        preprocessor_path,
    )

    def class_count(part: pd.DataFrame) -> dict[str, int]:
        return {str(key): int(value) for key, value in part["__target_binary"].value_counts().sort_index().items()}

    families = sorted(
        {str(value) for value in test_ready.loc[test_ready["__target_binary"] == 1, "__target_original"].unique()}
    )
    stats = {
        "dataset": {"id": dataset_id, "name": dataset["name"], "version": dataset["version"]},
        "target_column": target_column,
        "benign_labels": benign_labels,
        "attack_families": families,
        "before": {
            "rows": before_rows,
            "columns": dataset["cols"],
            "missing_cells": before_missing,
            "target_distribution": {str(k): int(v) for k, v in y_original.value_counts().head(30).items()},
        },
        "after": {
            "rows": int(len(frame)),
            "features": len(feature_names),
            "missing_cells": int(train_ready[feature_names].isna().sum().sum() +
                                 val_ready[feature_names].isna().sum().sum() +
                                 test_ready[feature_names].isna().sum().sum()),
            "target_distribution": class_count(pd.concat([train_ready, val_ready, test_ready])),
        },
        "removed": {
            "duplicates": duplicate_count,
            "incomplete_rows": incomplete_rows,
            "identifier_columns": identifier_columns,
            "dropped_columns": identifier_columns + high_missing_columns + constant_columns + list(explicit_drop),
            "high_missing_columns": high_missing_columns,
            "constant_columns": constant_columns,
        },
        "split": {
            "train_rows": int(len(train_ready)),
            "val_rows": int(len(val_ready)),
            "test_rows": int(len(test_ready)),
            "train_distribution": class_count(train_ready),
            "val_distribution": class_count(val_ready),
            "test_distribution": class_count(test_ready),
        },
        "config": {
            "missing_strategy": config.get("missing_strategy", "median"),
            "scaling": config.get("scaling", "standard"),
            "imbalance": imbalance,
            "oversampled_train_only": oversampled,
            "test_size": test_size,
            "val_size": val_size,
            "random_state": random_state,
            "top_k": int(config.get("top_k") or 0),
            "drop_identifiers": bool(config.get("drop_identifiers", True)),
            "remove_duplicates": bool(config.get("remove_duplicates", True)),
            "handle_infinite": bool(config.get("handle_infinite", True)),
            "max_rows": max_rows,
        },
        "leakage_controls": [
            "Duplicates were removed before the split.",
            "Imputers, encoders, scaling and feature selection were fitted on the training split only.",
            "Validation and test rows were transformed with the fitted training pipeline.",
            "Oversampling, when enabled, was applied after the split and only to the training split.",
            "Identifier-like columns were excluded from the feature matrix.",
        ],
        "sampled": sampled,
        "row_cap_applied": max_rows if sampled else None,
        "feature_names": feature_names[:400],
    }

    run_id = artifact_dir.name
    record = {
        "id": run_id,
        "dataset_id": dataset_id,
        "name": f"{dataset['name']} v{dataset['version']} · {run_id[-6:]}",
        "config_json": db.as_json(config),
        "stats_json": db.as_json(stats),
        "artifact_path": str(artifact_dir),
        "preprocessor_path": str(preprocessor_path),
        "target_column": target_column,
        "feature_names_json": db.as_json(feature_names),
        "families_json": db.as_json(families),
        "train_rows": int(len(train_ready)),
        "val_rows": int(len(val_ready)),
        "test_rows": int(len(test_ready)),
        "created_at": db.utc_now(),
    }
    db.insert("preprocess_runs", record)
    job.update(1.0, "Preprocessing complete")
    return preprocess_record(record, stats=stats)


def preprocess_record(row: dict[str, Any], stats: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "dataset_id": row["dataset_id"],
        "name": row["name"],
        "target_column": row["target_column"],
        "feature_names": db.parse_json(row.get("feature_names_json"), []),
        "families": db.parse_json(row.get("families_json"), []),
        "train_rows": row["train_rows"],
        "val_rows": row["val_rows"],
        "test_rows": row["test_rows"],
        "created_at": row["created_at"],
        "stats": stats if stats is not None else db.parse_json(row.get("stats_json"), {}),
        "config": db.parse_json(row.get("config_json"), {}),
    }


def list_runs(dataset_id: str | None = None) -> list[dict[str, Any]]:
    if dataset_id:
        rows = db.query_all(
            "SELECT * FROM preprocess_runs WHERE dataset_id = ? ORDER BY created_at DESC", (dataset_id,)
        )
    else:
        rows = db.query_all("SELECT * FROM preprocess_runs ORDER BY created_at DESC")
    return [preprocess_record(row) for row in rows]


def get_run(run_id: str) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM preprocess_runs WHERE id = ?", (run_id,))
    if not row:
        raise PreprocessError("Preprocessing run not found.")
    return preprocess_record(row)


def get_run_row(run_id: str) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM preprocess_runs WHERE id = ?", (run_id,))
    if not row:
        raise PreprocessError("Preprocessing run not found.")
    return row


def load_preprocessor(row: dict[str, Any]) -> dict[str, Any]:
    path = Path(row["preprocessor_path"])
    if not path.exists():
        raise PreprocessError("The fitted preprocessor artifact is missing. Re-run preprocessing.")
    return joblib.load(path)


def load_splits(row: dict[str, Any]) -> dict[str, pd.DataFrame]:
    artifact = Path(row["artifact_path"])
    return {
        "train": pd.read_parquet(artifact / "train.parquet"),
        "val": pd.read_parquet(artifact / "val.parquet"),
        "test": pd.read_parquet(artifact / "test.parquet"),
        "test_raw": pd.read_parquet(artifact / "test_raw.parquet"),
        "meta": db.parse_json(row["stats_json"], {}),
    }
