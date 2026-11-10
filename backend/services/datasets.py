"""Dataset services: upload, profiling, versioning, preview and Kaggle import."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import db, settings
from ..jobs import Job

SUPPORTED_SUFFIXES = {".csv", ".parquet"}
TARGET_HINTS = re.compile(
    r"(^label$|label|attack|^class$|class_|category|^target$|malicious|^type$|anomaly|^normal$)", re.I
)
IDENTIFIER_HINT = re.compile(r"(^id$|_id$|^id_|flow.?id|session.?id|src.?ip|dst.?ip|source|destination)", re.I)

KAGGLE_PRESETS: list[dict[str, str]] = [
    {
        "key": "edgeiiotset",
        "label": "Edge-IIoTset",
        "slug": "mohamedamineferrag/edgeiiotset-cyber-security-dataset-of-iot-iiot",
        "url": "https://www.kaggle.com/datasets/mohamedamineferrag/edgeiiotset-cyber-security-dataset-of-iot-iiot",
        "description": "IoT/IIoT telemetry with multiple attack families and a Label column.",
        "target_hint": "Label",
    },
    {
        "key": "ciciot2023",
        "label": "CICIoT2023",
        "slug": "akashdogra/cic-iot-2023",
        "url": "https://www.kaggle.com/datasets/akashdogra/cic-iot-2023",
        "description": "CIC IoT 2023 flow features with a multi-class attack label.",
        "target_hint": "label",
    },
    {
        "key": "toniot",
        "label": "ToN_IoT",
        "slug": "arnobbhowmik/ton-iot-network-dataset",
        "url": "https://www.kaggle.com/datasets/arnobbhowmik/ton-iot-network-dataset",
        "description": "ToN-IoT network records covering normal traffic and attack categories.",
        "target_hint": "type",
    },
]

BENIGN_TOKENS = {
    "benign", "normal", "normal traffic", "benign traffic", "legitimate", "legit",
    "no attack", "no_attack", "none", "0", "0.0", "false", "clean",
}


class DatasetError(ValueError):
    """A dataset problem that should be shown to the user as a 4xx response."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return stem or "dataset"


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (np.ndarray,)):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _serialize_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        records.append({str(key): _json_value(value) for key, value in record.items()})
    return records


def _read_head(path: Path, fmt: str, limit: int) -> pd.DataFrame:
    if fmt == "parquet":
        return pd.read_parquet(path).head(limit)
    return pd.read_csv(path, nrows=limit, low_memory=False)


def _class_distribution(frame: pd.DataFrame, column: str | None, limit: int = 30) -> dict[str, int]:
    if not column or column not in frame.columns:
        return {}
    counts = frame[column].astype("string").fillna("(missing)").value_counts().head(limit)
    return {str(key): int(value) for key, value in counts.items()}


def _target_candidates(frame: pd.DataFrame) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for column in frame.columns:
        series = frame[column]
        unique = series.nunique(dropna=True)
        is_object = series.dtype == object or str(series.dtype).startswith("string")
        hinted = bool(TARGET_HINTS.search(str(column)))
        if not hinted and not (is_object and 2 <= unique <= 40):
            continue
        counts = series.astype("string").fillna("(missing)").value_counts().head(12)
        candidates.append(
            {
                "column": str(column),
                "dtype": str(series.dtype),
                "unique": int(unique),
                "hinted": hinted,
                "top_values": [{"value": str(k), "count": int(v)} for k, v in counts.items()],
            }
        )
    candidates.sort(key=lambda item: (not item["hinted"], item["unique"]))
    return candidates[:14]


def _pick_target(candidates: list[dict[str, Any]], columns: list[str]) -> str | None:
    priority = ["label", "attack_type", "attack_cat", "attack", "class", "type", "target", "category"]
    lowered = {column.lower(): column for column in columns}
    for name in priority:
        if name in lowered:
            return lowered[name]
    for candidate in candidates:
        if candidate["hinted"]:
            return candidate["column"]
    return None


def profile_file(path: Path, fmt: str, sample_limit: int = 50_000) -> dict[str, Any]:
    """Profile a CSV/Parquet file, streaming CSVs so large files stay bounded."""
    sample = _read_head(path, fmt, sample_limit)
    columns = [str(column) for column in sample.columns]
    dtypes = {str(column): str(dtype) for column, dtype in sample.dtypes.items()}
    missing = {str(column): int(value) for column, value in sample.isna().sum().items()}
    duplicates = int(sample.duplicated().sum())
    duplicates_exact = len(sample) < sample_limit
    rows = len(sample)

    if fmt == "csv":
        rows = 0
        missing_total = pd.Series(0, index=sample.columns, dtype="int64")
        seen: set[int] = set()
        over_limit = False
        try:
            for chunk in pd.read_csv(path, chunksize=100_000, low_memory=False):
                rows += len(chunk)
                missing_total = missing_total.add(chunk.isna().sum(), fill_value=0)
                if not over_limit and rows <= 1_000_000:
                    seen.update(int(value) for value in pd.util.hash_pandas_object(chunk, index=False))
                else:
                    over_limit = True
                    seen = set()
            missing = {str(column): int(value) for column, value in missing_total.items()}
            if not over_limit:
                duplicates = int(rows - len(seen))
                duplicates_exact = True
            else:
                duplicates = int(round(sample.duplicated().mean() * rows))
                duplicates_exact = False
        except pd.errors.ParserError as exc:
            raise DatasetError(f"The CSV file could not be parsed: {exc}") from exc
    else:
        try:
            import pyarrow.parquet as pq

            rows = int(pq.ParquetFile(path).metadata.num_rows)
            if rows > sample_limit:
                missing = {key: int(round(value / max(len(sample), 1) * rows)) for key, value in missing.items()}
        except Exception:  # noqa: BLE001 - metadata is optional
            rows = len(sample)
        duplicates_exact = rows <= sample_limit

    candidates = _target_candidates(sample)
    target = _pick_target(candidates, columns)
    return {
        "rows": int(rows),
        "cols": len(columns),
        "columns": columns,
        "dtypes": dtypes,
        "missing": missing,
        "duplicates": int(max(duplicates, 0)),
        "duplicates_exact": duplicates_exact,
        "target_candidates": candidates,
        "suggested_target": target,
        "class_distribution": _class_distribution(sample, target),
        "profiled_rows": int(len(sample)),
        "profile_sampled": rows > sample_limit,
    }


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def _next_version(name: str) -> tuple[int, str | None]:
    existing = db.query_all(
        "SELECT id, version FROM datasets WHERE name = ? ORDER BY version DESC LIMIT 1", (name,)
    )
    if not existing:
        return 1, None
    return int(existing[0]["version"]) + 1, existing[0]["id"]


def import_path(
    source: Path,
    original_filename: str,
    origin: str = "upload",
    notes: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    suffix = Path(original_filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise DatasetError("Only CSV and Parquet files are supported.")
    if not source.exists() or source.stat().st_size == 0:
        raise DatasetError("The file is empty.")

    dataset_name = name or _safe_stem(original_filename)
    version, parent_id = _next_version(dataset_name)
    dataset_id = db.new_id("ds_")
    stored_name = f"{dataset_id}__{_safe_stem(original_filename)}{suffix}"
    destination = settings.DATASET_DIR / stored_name
    shutil.copy2(source, destination)

    fmt = "csv" if suffix == ".csv" else "parquet"
    profile = profile_file(destination, fmt)
    record = {
        "id": dataset_id,
        "name": dataset_name,
        "version": version,
        "parent_id": parent_id,
        "origin": origin,
        "filename": original_filename,
        "stored_path": str(destination),
        "format": fmt,
        "size_bytes": int(destination.stat().st_size),
        "rows": profile["rows"],
        "cols": profile["cols"],
        "target_column": profile["suggested_target"],
        "columns_json": db.as_json(profile["columns"]),
        "dtypes_json": db.as_json(profile["dtypes"]),
        "missing_json": db.as_json(profile["missing"]),
        "duplicates": profile["duplicates"],
        "class_distribution_json": db.as_json(profile["class_distribution"]),
        "target_candidates_json": db.as_json(profile["target_candidates"]),
        "status": "ready",
        "notes": notes,
        "created_at": db.utc_now(),
    }
    db.insert("datasets", record)
    return dataset_record(record)


def dataset_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "version": row["version"],
        "parent_id": row.get("parent_id"),
        "origin": row["origin"],
        "filename": row["filename"],
        "format": row["format"],
        "size_bytes": row["size_bytes"],
        "rows": row["rows"],
        "cols": row["cols"],
        "target_column": row.get("target_column"),
        "columns": db.parse_json(row.get("columns_json"), []),
        "dtypes": db.parse_json(row.get("dtypes_json"), {}),
        "missing": db.parse_json(row.get("missing_json"), {}),
        "duplicates": row.get("duplicates", 0),
        "class_distribution": db.parse_json(row.get("class_distribution_json"), {}),
        "target_candidates": db.parse_json(row.get("target_candidates_json"), []),
        "status": row["status"],
        "notes": row.get("notes"),
        "created_at": row["created_at"],
    }


def list_datasets() -> list[dict[str, Any]]:
    rows = db.query_all("SELECT * FROM datasets ORDER BY created_at DESC")
    return [dataset_record(row) for row in rows]


def get_dataset(dataset_id: str) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    if not row:
        raise DatasetError("Dataset not found.")
    return dataset_record(row)


def get_dataset_row(dataset_id: str) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    if not row:
        raise DatasetError("Dataset not found.")
    return row


def set_target(dataset_id: str, target_column: str) -> dict[str, Any]:
    row = get_dataset_row(dataset_id)
    columns = db.parse_json(row["columns_json"], [])
    if target_column not in columns:
        raise DatasetError(f"Column '{target_column}' does not exist in this dataset.")
    frame = _read_head(Path(row["stored_path"]), row["format"], 100_000)
    distribution = _class_distribution(frame, target_column)
    db.execute(
        "UPDATE datasets SET target_column = ?, class_distribution_json = ? WHERE id = ?",
        (target_column, db.as_json(distribution), dataset_id),
    )
    return get_dataset(dataset_id)


def preview(dataset_id: str, limit: int = 50) -> dict[str, Any]:
    row = get_dataset_row(dataset_id)
    frame = _read_head(Path(row["stored_path"]), row["format"], max(1, min(limit, 200)))
    profile = []
    for column in frame.columns:
        series = frame[column]
        profile.append(
            {
                "column": str(column),
                "dtype": str(series.dtype),
                "missing": int(series.isna().sum()),
                "unique": int(series.nunique(dropna=True)),
                "sample": [_json_value(value) for value in series.dropna().head(3).tolist()],
            }
        )
    return {
        "dataset_id": dataset_id,
        "rows": frame.shape[0],
        "columns": [str(column) for column in frame.columns],
        "records": _serialize_frame(frame),
        "profile": profile,
    }


def delete_dataset(dataset_id: str) -> None:
    row = get_dataset_row(dataset_id)
    runs = db.query_all("SELECT * FROM preprocess_runs WHERE dataset_id = ?", (dataset_id,))
    for run in runs:
        shutil.rmtree(Path(run["artifact_path"]).parent, ignore_errors=True)
        experiments = db.query_all("SELECT * FROM experiments WHERE preprocess_id = ?", (run["id"],))
        for experiment in experiments:
            for key in ("artifact_path", "preprocessor_path", "predictions_path"):
                if experiment.get(key):
                    Path(experiment[key]).unlink(missing_ok=True)
        db.execute("DELETE FROM experiments WHERE preprocess_id = ?", (run["id"],))
    db.execute("DELETE FROM preprocess_runs WHERE dataset_id = ?", (dataset_id,))
    Path(row["stored_path"]).unlink(missing_ok=True)
    db.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))


def read_frame(dataset_id: str) -> pd.DataFrame:
    row = get_dataset_row(dataset_id)
    path = Path(row["stored_path"])
    if row["format"] == "parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


# --------------------------------------------------------------------------- #
# Kaggle
# --------------------------------------------------------------------------- #
def _kaggle_credentials() -> tuple[str, str, str]:
    username = os.environ.get("KAGGLE_USERNAME", "").strip()
    key = os.environ.get("KAGGLE_KEY", "").strip()
    if username and key:
        return username, key, "environment"
    config_candidates = []
    if os.environ.get("KAGGLE_CONFIG_DIR"):
        config_candidates.append(Path(os.environ["KAGGLE_CONFIG_DIR"]) / "kaggle.json")
    config_candidates.append(Path.home() / ".kaggle" / "kaggle.json")
    for config_path in config_candidates:
        if config_path.exists():
            try:
                payload = json.loads(config_path.read_text(encoding="utf-8"))
                username = str(payload.get("username", "")).strip()
                key = str(payload.get("key", "")).strip()
                if username and key:
                    return username, key, str(config_path)
            except (OSError, ValueError):
                continue
    return "", "", ""


def kaggle_status() -> dict[str, Any]:
    username, key, source = _kaggle_credentials()
    return {
        "configured": bool(username and key),
        "source": source,
        "hint": (
            "Kaggle credentials are configured on the backend."
            if username and key
            else "Set KAGGLE_USERNAME and KAGGLE_KEY on the backend, or upload a dataset you downloaded manually."
        ),
    }


def kaggle_presets() -> list[dict[str, str]]:
    return KAGGLE_PRESETS


def _download_kaggle_archive(slug: str, job: Job) -> Path:
    username, key, _ = _kaggle_credentials()
    if not (username and key):
        raise DatasetError(
            "Kaggle credentials are not configured. Set KAGGLE_USERNAME and KAGGLE_KEY "
            "in the backend environment (never in the frontend), or upload the CSV manually."
        )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", slug):
        raise DatasetError("Kaggle dataset reference must look like 'owner/dataset-slug'.")

    target = settings.KAGGLE_DIR / f"{slug.replace('/', '__')}.zip"
    target.unlink(missing_ok=True)
    token = base64.b64encode(f"{username}:{key}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        f"https://www.kaggle.com/api/v1/datasets/download/{slug}",
        headers={"Authorization": f"Basic {token}", "User-Agent": "EdgeGuardAI/1.0"},
    )
    job.update(0.05, f"Requesting {slug} from Kaggle")
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=120) as response, open(target, "wb") as handle:
            content_length = int(response.headers.get("Content-Length") or 0)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.MAX_KAGGLE_BYTES:
                    handle.close()
                    target.unlink(missing_ok=True)
                    raise DatasetError("The Kaggle archive exceeds the configured size limit.")
                handle.write(chunk)
                if content_length:
                    job.update(0.05 + 0.5 * total / content_length,
                               f"Downloading archive ({total // (1024 * 1024)} MB)")
    except urllib.error.HTTPError as exc:
        target.unlink(missing_ok=True)
        if exc.code == 401:
            raise DatasetError("Kaggle rejected the credentials (HTTP 401). Check KAGGLE_USERNAME/KAGGLE_KEY.") from exc
        if exc.code == 403:
            raise DatasetError(
                "Kaggle returned 403. Accept the dataset rules on Kaggle with this account first."
            ) from exc
        if exc.code == 404:
            raise DatasetError("Kaggle dataset not found. Check the owner/slug reference.") from exc
        raise DatasetError(f"Kaggle download failed with HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        target.unlink(missing_ok=True)
        raise DatasetError(f"Could not reach Kaggle: {exc.reason}") from exc
    return target


def _safe_extract(archive: Path) -> list[Path]:
    destination = settings.KAGGLE_DIR / archive.stem
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(archive) as bundle:
        members = [info for info in bundle.infolist() if not info.is_dir()]
        declared = sum(info.file_size for info in members)
        if declared > settings.MAX_KAGGLE_BYTES:
            raise DatasetError("The extracted Kaggle archive exceeds the configured size limit.")
        for info in members:
            suffix = Path(info.filename).suffix.lower()
            if suffix not in SUPPORTED_SUFFIXES or "__MACOSX" in info.filename:
                continue
            relative = Path(info.filename)
            if relative.is_absolute() or ".." in relative.parts:
                continue
            output = destination / relative.name
            counter = 1
            while output.exists():
                output = destination / f"{relative.stem}_{counter}{relative.suffix}"
                counter += 1
            with bundle.open(info) as source, open(output, "wb") as handle:
                shutil.copyfileobj(source, handle)
            extracted.append(output)
    return extracted


def _is_zip(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            return handle.read(4) == b"PK\x03\x04"
    except OSError:
        return False


def import_kaggle(slug: str, job: Job) -> list[dict[str, Any]]:
    archive = _download_kaggle_archive(slug, job)
    job.update(0.6, "Download complete, extracting")
    if _is_zip(archive):
        files = _safe_extract(archive)
    else:
        suffix = ".csv" if archive.suffix.lower() != ".parquet" else ".parquet"
        fallback = archive.with_suffix(suffix)
        archive.rename(fallback)
        files = [fallback]
    if not files:
        raise DatasetError("No CSV or Parquet files were found in the Kaggle archive.")
    imported: list[dict[str, Any]] = []
    for index, path in enumerate(files[:8]):
        job.update(0.65 + 0.3 * index / max(len(files[:8]), 1), f"Profiling {path.name}")
        imported.append(
            import_path(
                path,
                path.name,
                origin="kaggle",
                notes=f"Imported from Kaggle dataset {slug}",
                name=f"{slug.split('/')[-1]}__{_safe_stem(path.name)}",
            )
        )
    job.update(0.99, f"Imported {len(imported)} file(s)")
    return imported


def export_dataset_csv(dataset_id: str) -> pd.DataFrame:
    return read_frame(dataset_id)


def optional_kaggle_cli(slug: str, job: Job) -> Path:
    """Fallback helper kept for environments that only expose the Kaggle CLI."""
    job.update(0.05, "Trying the Kaggle CLI")
    output = settings.KAGGLE_DIR / slug.replace("/", "__")
    output.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, "-m", "kaggle", "datasets", "download", "-d", slug, "-p", str(output), "--unzip"],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if result.returncode != 0:
        raise DatasetError(f"Kaggle CLI failed: {result.stderr.strip() or result.stdout.strip()}")
    candidates = [path for path in output.rglob("*") if path.suffix.lower() in SUPPORTED_SUFFIXES]
    if not candidates:
        raise DatasetError("Kaggle CLI produced no CSV/Parquet files.")
    return candidates[0]
