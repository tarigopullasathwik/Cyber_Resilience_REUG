"""Unknown-attack evaluation.

Two honest experimental designs are implemented:

* **holdout** - one or more attack families are removed from every training and
  validation split; a supervised detector is trained on the remaining families,
  and an anomaly detector is trained on benign traffic only. Both are then
  measured on the withheld families.
* **lofo** - leave-one-attack-family-out: for every family a fresh detector is
  trained without that family and evaluated on it. This is repeated, never
  faked, and the per-family results are reported individually.

Held-out recall is a proxy for unknown-attack sensitivity, not proof of
zero-day detection. The UI and report say so explicitly.
"""

from __future__ import annotations

from typing import Any

import joblib
import numpy as np
import pandas as pd

from .. import db, settings
from ..jobs import Job
from . import modeling, preprocessing


class UnknownError(ValueError):
    pass


def _prepare(experiment_row: dict[str, Any]) -> dict[str, Any]:
    run_row = preprocessing.get_run_row(experiment_row["preprocess_id"])
    splits = preprocessing.load_splits(run_row)
    feature_names = db.parse_json(run_row["feature_names_json"], [])
    if not feature_names:
        feature_names = [c for c in splits["train"].columns if not c.startswith("__target")]
    families = sorted(
        {
            str(value)
            for value in pd.concat([splits["train"], splits["test"]])["__target_original"]
            .astype(str)
            .unique()
            if str(value).lower() not in {label.lower() for label in db.parse_json(
                run_row["stats_json"], {}
            ).get("benign_labels", [])}
        }
    )
    families_in_test = sorted(
        {str(value) for value in splits["test"].loc[splits["test"]["__target_binary"] == 1,
                                                     "__target_original"].unique()}
    )
    return {
        "run_row": run_row,
        "splits": splits,
        "feature_names": feature_names,
        "families": families,
        "families_in_test": families_in_test,
    }


def available_families(preprocess_id: str) -> dict[str, Any]:
    row = preprocessing.get_run_row(preprocess_id)
    splits = preprocessing.load_splits(row)
    stats = db.parse_json(row["stats_json"], {})
    benign = {str(label).lower() for label in stats.get("benign_labels", [])}
    attack = splits["test"][splits["test"]["__target_binary"] == 1]
    families = sorted({str(value) for value in attack["__target_original"].unique()})
    counts = {
        str(key): int(value)
        for key, value in attack["__target_original"].astype(str).value_counts().items()
    }
    train_attack = splits["train"][splits["train"]["__target_binary"] == 1]
    train_counts = {
        str(key): int(value)
        for key, value in train_attack["__target_original"].astype(str).value_counts().items()
    }
    return {
        "preprocess_id": preprocess_id,
        "families": families,
        "test_counts": counts,
        "train_counts": train_counts,
        "benign_labels": list(benign),
    }


def _fit_pair(
    train: pd.DataFrame,
    val: pd.DataFrame,
    feature_names: list[str],
    params: dict[str, Any],
    random_state: int,
) -> dict[str, Any]:
    x_train = train[feature_names].to_numpy(dtype=np.float32)
    y_train = train["__target_binary"].to_numpy(dtype=int)
    benign_mask = y_train == 0
    if benign_mask.sum() < 20:
        raise UnknownError("Not enough benign training rows for a held-out-family experiment.")

    supervised_name = params.get("supervised_model", "random_forest")
    supervised_params = params.get("supervised_params") or {
        "n_estimators": int(params.get("n_estimators", 160)),
        "max_depth": params.get("max_depth"),
        "class_weight": "balanced_subsample",
    }
    supervised = modeling.build_model(
        supervised_name, supervised_params, random_state, class_balance=1.0
    )
    supervised.fit(x_train, y_train)

    anomaly_name = params.get("anomaly_model", "isolation_forest")
    anomaly_params = params.get("anomaly_params") or {
        "n_estimators": int(params.get("anomaly_estimators", 120)),
    }
    anomaly = modeling.build_model(anomaly_name, anomaly_params, random_state)
    benign_train = x_train[benign_mask]
    if anomaly_name == "one_class_svm" and len(benign_train) > 6000:
        rng = np.random.default_rng(random_state)
        benign_train = benign_train[rng.choice(len(benign_train), 6000, replace=False)]
    anomaly.fit(benign_train)

    val_benign = val[val["__target_binary"] == 0]
    x_ref = (
        val_benign[feature_names].to_numpy(dtype=np.float32)
        if len(val_benign) >= 20
        else benign_train
    )
    raw_ref = modeling._raw_scores(anomaly, x_ref)
    lo = float(np.percentile(raw_ref, 1))
    hi = float(np.percentile(raw_ref, 99.5))
    threshold = float(
        np.quantile(modeling.normalize_scores(raw_ref, lo, hi),
                    float(params.get("threshold_quantile", 0.99)))
    )
    threshold = max(0.02, min(0.98, threshold))

    def scores(features: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        supervised_score = np.asarray(supervised.predict_proba(features))[:, 1]
        anomaly_score = modeling.normalize_scores(
            modeling._raw_scores(anomaly, features), lo, hi
        )
        fused = np.maximum(supervised_score, anomaly_score)
        return supervised_score, anomaly_score, fused

    return {
        "supervised": supervised,
        "anomaly": anomaly,
        "supervised_name": supervised_name,
        "anomaly_name": anomaly_name,
        "threshold": threshold,
        "norm_low": lo,
        "norm_high": hi,
        "scores": scores,
    }


def run_unknown(experiment_id: str, job: Job) -> dict[str, Any]:
    row = modeling.get_experiment_row(experiment_id)
    params = db.parse_json(row["params_json"], {})
    preprocess_id = row["preprocess_id"]
    if not preprocess_id:
        raise UnknownError("Select a preprocessing run first.")
    prepared = _prepare(row)
    splits = prepared["splits"]
    feature_names = prepared["feature_names"]
    train, val, test = splits["train"], splits["val"], splits["test"]
    family_train = train["__target_original"].astype(str)
    family_test = test["__target_original"].astype(str)
    y_test = test["__target_binary"].to_numpy(dtype=int)
    mode = params.get("mode", "holdout")
    heldout = [str(family) for family in params.get("holdout_families", [])]

    known_families = [
        family for family in prepared["families"]
        if family.lower() not in {label.lower() for label in
                                  db.parse_json(prepared["run_row"]["stats_json"], {}).get("benign_labels", [])}
    ]
    if mode == "holdout":
        if not heldout:
            heldout = prepared["families_in_test"][:1]
        if not heldout:
            raise UnknownError("No attack families are available in the test split to withhold.")
        missing = [family for family in heldout if family not in prepared["families_in_test"]]
        if missing:
            raise UnknownError(
                "These families do not occur as attacks in the test split: " + ", ".join(missing)
            )

    random_state = int(params.get("random_state", 42))
    max_train_rows = int(params.get("max_train_rows", 60000))

    # --- primary withheld-family experiment ---------------------------------- #
    job.update(0.08, "Preparing withheld-family training data")
    if mode == "holdout":
        train_subset = train[~family_train.isin(heldout)].copy()
    else:
        train_subset = train.copy()
    if len(train_subset) > max_train_rows:
        train_subset = train_subset.sample(max_train_rows, random_state=random_state)

    job.update(0.2, "Fitting supervised and anomaly detectors without the withheld families")
    pair = _fit_pair(train_subset, val, feature_names, params, random_state)
    x_test = test[feature_names].to_numpy(dtype=np.float32)
    supervised_score, anomaly_score, fused_score = pair["scores"](x_test)

    known_mask = (y_test == 1) & (~family_test.isin(heldout))
    unknown_mask = (y_test == 1) & (family_test.isin(heldout))
    benign_mask = y_test == 0
    threshold = pair["threshold"]
    supervised_pred = supervised_score >= 0.5
    anomaly_pred = anomaly_score >= threshold
    fused_pred = fused_score >= max(threshold, 0.5) if mode != "holdout" else (
        supervised_pred | anomaly_pred
    )

    subset_scores = fused_score[benign_mask | known_mask]
    subset_labels = y_test[benign_mask | known_mask]
    known_eval = modeling._evaluate(
        subset_labels,
        subset_scores,
        max(threshold, 0.5),
        family_test[benign_mask | known_mask].to_numpy(),
    )

    def rate(mask: np.ndarray, prediction: np.ndarray) -> float | None:
        return round(float(prediction[mask].mean()), 6) if int(mask.sum()) else None

    metrics = {
        "mode": mode,
        "heldout_families": heldout,
        "known_attack_recall": rate(known_mask, fused_pred),
        "unknown_attack_recall": rate(unknown_mask, fused_pred),
        "supervised_known_recall": rate(known_mask, supervised_pred),
        "supervised_unknown_recall": rate(unknown_mask, supervised_pred),
        "anomaly_known_recall": rate(known_mask, anomaly_pred),
        "anomaly_unknown_recall": rate(unknown_mask, anomaly_pred),
        "benign_false_positive_rate": rate(benign_mask, fused_pred),
        "supervised_benign_fpr": rate(benign_mask, supervised_pred),
        "anomaly_benign_fpr": rate(benign_mask, anomaly_pred),
        "unknown_mean_score": round(float(fused_score[unknown_mask].mean()), 6) if unknown_mask.sum() else None,
        "known_mean_score": round(float(fused_score[known_mask].mean()), 6) if known_mask.sum() else None,
        "benign_mean_score": round(float(fused_score[benign_mask].mean()), 6) if benign_mask.sum() else None,
        "n_unknown": int(unknown_mask.sum()),
        "n_known": int(known_mask.sum()),
        "n_benign": int(benign_mask.sum()),
        "threshold": round(float(threshold), 6),
        "supervised_model": pair["supervised_name"],
        "anomaly_model": pair["anomaly_name"],
        "roc_auc_known_vs_benign": known_eval["metrics"].get("roc_auc"),
        "precision_known_vs_benign": known_eval["metrics"].get("precision"),
        "n_train": int(len(train_subset)),
        "n_features": len(feature_names),
        "test_rows": int(len(test)),
    }
    per_family = []
    for family in sorted(set(family_test[y_test == 1])):
        mask = (family_test == family).to_numpy()
        support = int(mask.sum())
        per_family.append(
            {
                "family": family,
                "support": support,
                "withheld": family in heldout,
                "supervised_recall": rate(mask, supervised_pred),
                "anomaly_recall": rate(mask, anomaly_pred),
                "fused_recall": rate(mask, fused_pred),
                "mean_score": round(float(fused_score[mask].mean()), 6),
            }
        )

    # --- leave-one-family-out ------------------------------------------------- #
    lofo_rows: list[dict[str, Any]] = []
    if mode == "lofo":
        candidates = [family for family in prepared["families_in_test"] if family in known_families]
        max_families = int(params.get("max_families", 5))
        candidates = candidates[:max_families]
        for index, family in enumerate(candidates):
            job.update(
                0.35 + 0.5 * index / max(len(candidates), 1),
                f"Leave-one-family-out: withholding {family} ({index + 1}/{len(candidates)})",
            )
            subset = train[~family_train.isin([family])]
            if int((subset["__target_binary"] == 1).sum()) < 10:
                lofo_rows.append(
                    {"family": family, "skipped": "not enough remaining attack rows", "support": 0}
                )
                continue
            if len(subset) > max_train_rows:
                subset = subset.sample(max_train_rows, random_state=random_state)
            try:
                fold = _fit_pair(subset, val, feature_names, params, random_state)
                fold_scores = fold["scores"](x_test)
                fold_fused = fold_scores[2] >= max(fold["threshold"], 0.5)
                fold_anomaly = fold_scores[1] >= fold["threshold"]
                mask = (family_test == family).to_numpy()
                lofo_rows.append(
                    {
                        "family": family,
                        "support": int(mask.sum()),
                        "fused_recall": rate(mask, fold_fused),
                        "anomaly_recall": rate(mask, fold_anomaly),
                        "benign_fpr": rate(benign_mask, fold_fused),
                        "mean_score": round(float(fold_scores[2][mask].mean()), 6),
                        "threshold": round(float(fold["threshold"]), 6),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - one fold must not abort the study
                lofo_rows.append({"family": family, "support": 0, "skipped": str(exc)})
        valid = [item for item in lofo_rows if item.get("fused_recall") is not None]
        if valid:
            metrics["lofo_mean_unknown_recall"] = round(
                float(np.mean([item["fused_recall"] for item in valid])), 6
            )
            metrics["lofo_mean_benign_fpr"] = round(
                float(np.mean([item.get("benign_fpr") or 0.0 for item in valid])), 6
            )
            metrics["lofo_families_evaluated"] = len(valid)
            metrics["unknown_attack_recall"] = metrics["lofo_mean_unknown_recall"]
            metrics["unknown_recall_kind"] = "lofo_mean"
            metrics["heldout_families"] = [item["family"] for item in valid]
        metrics["mode"] = "lofo"

    # --- score distribution for the UI ---------------------------------------- #
    bins = np.linspace(0, 1, 21)
    histogram = []
    for index in range(len(bins) - 1):
        low, high = bins[index], bins[index + 1]
        histogram.append(
            {
                "bin": f"{low:.2f}",
                "benign": int(((fused_score[benign_mask] >= low) & (fused_score[benign_mask] < high)).sum()),
                "known": int(((fused_score[known_mask] >= low) & (fused_score[known_mask] < high)).sum()),
                "unknown": int(((fused_score[unknown_mask] >= low) & (fused_score[unknown_mask] < high)).sum()),
            }
        )
    composition = {
        "benign": int(benign_mask.sum()),
        "known_malicious": int(((fused_pred) & known_mask).sum()),
        "known_missed": int(((~fused_pred) & known_mask).sum()),
        "suspected_unknown": int(((fused_pred) & unknown_mask).sum()),
        "unknown_missed": int(((~fused_pred) & unknown_mask).sum()),
    }

    # --- persist --------------------------------------------------------------- #
    experiment_dir = settings.ARTIFACT_DIR / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = settings.MODEL_DIR / f"{experiment_id}.joblib"
    joblib.dump(
        {
            "supervised": pair["supervised"],
            "anomaly": pair["anomaly"],
            "supervised_name": pair["supervised_name"],
            "anomaly_name": pair["anomaly_name"],
            "feature_names": feature_names,
            "threshold": threshold,
            "norm_low": pair["norm_low"],
            "norm_high": pair["norm_high"],
            "preprocessor_path": prepared["run_row"]["preprocessor_path"],
            "kind": "unknown",
        },
        artifact_path,
    )
    predictions = pd.DataFrame(
        {
            "row_index": np.arange(len(y_test)),
            "score": fused_score,
            "score_supervised": supervised_score,
            "score_anomaly": anomaly_score,
            "predicted": fused_pred.astype(int),
            "y_binary": y_test,
            "y_family": family_test,
            "withheld": family_test.isin(heldout).to_numpy(),
        }
    )
    predictions_path = experiment_dir / "test_predictions.parquet"
    predictions.to_parquet(predictions_path, index=False)

    curves = {
        "score_histogram": histogram,
        "composition": composition,
        "known_vs_benign": {
            "roc": known_eval["curves"].get("roc", []),
            "pr": known_eval["curves"].get("pr", []),
        },
        "per_family": per_family,
        "lofo": lofo_rows,
        "known_vs_benign_scores": {
            "benign": [float(value) for value in fused_score[benign_mask][:2500]],
            "known": [float(value) for value in fused_score[known_mask][:2500]],
            "unknown": [float(value) for value in fused_score[unknown_mask][:2500]],
        },
    }
    db.update(
        "experiments",
        experiment_id,
        {
            "status": "completed",
            "progress": 1.0,
            "message": "Unknown-attack evaluation complete",
            "metrics_json": db.as_json(metrics),
            "curves_json": db.as_json(curves),
            "confusion_json": db.as_json(known_eval["metrics"]),
            "per_class_json": db.as_json(known_eval["per_class"]),
            "per_family_json": db.as_json(lofo_rows if mode == "lofo" else per_family),
            "feature_importance_json": db.as_json(
                modeling._feature_importance(pair["supervised"], feature_names)
            ),
            "artifact_path": str(artifact_path),
            "preprocessor_path": prepared["run_row"]["preprocessor_path"],
            "predictions_path": str(predictions_path),
            "completed_at": db.utc_now(),
        },
    )
    job.update(1.0, "Held-out evaluation complete")
    return modeling.get_experiment(experiment_id)

