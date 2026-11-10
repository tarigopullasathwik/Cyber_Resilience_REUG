"""API routes for dataset management and Kaggle import."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import jobs as job_registry
from .. import settings
from ..services import datasets

router = APIRouter(prefix="/api", tags=["datasets"])


class TargetRequest(BaseModel):
    target_column: str = Field(min_length=1, max_length=256)


class KaggleImportRequest(BaseModel):
    slug: str = Field(min_length=3, max_length=256)
    preset: str | None = None


@router.get("/datasets")
def list_datasets() -> list[dict[str, Any]]:
    return datasets.list_datasets()


@router.post("/datasets/upload", status_code=201)
def upload_dataset(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = file.filename or "upload.csv"
    suffix = Path(filename).suffix.lower()
    if suffix not in datasets.SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Only .csv and .parquet files are supported.")
    temporary_path: Path | None = None
    size = 0
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, dir=settings.DATASET_DIR, suffix=suffix
        ) as handle:
            temporary_path = Path(handle.name)
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.",
                    )
                handle.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        dataset = datasets.import_path(temporary_path, filename, origin="upload")
        return dataset
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict[str, Any]:
    return datasets.get_dataset(dataset_id)


@router.get("/datasets/{dataset_id}/preview")
def preview_dataset(dataset_id: str, limit: int = 50) -> dict[str, Any]:
    return datasets.preview(dataset_id, limit)


@router.patch("/datasets/{dataset_id}/target")
def set_target(dataset_id: str, body: TargetRequest) -> dict[str, Any]:
    return datasets.set_target(dataset_id, body.target_column)


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str) -> None:
    datasets.delete_dataset(dataset_id)


@router.get("/kaggle/status")
def kaggle_status() -> dict[str, Any]:
    return {"status": datasets.kaggle_status(), "presets": datasets.kaggle_presets()}


@router.get("/kaggle/presets")
def kaggle_presets() -> list[dict[str, str]]:
    return datasets.kaggle_presets()


@router.post("/kaggle/import", status_code=202)
def import_kaggle(body: KaggleImportRequest) -> dict[str, Any]:
    if not datasets.kaggle_status()["configured"]:
        raise HTTPException(
            status_code=400,
            detail="Kaggle credentials are not configured on the backend. Set KAGGLE_USERNAME "
                   "and KAGGLE_KEY, or upload a downloaded CSV/Parquet file.",
        )
    job = job_registry.jobs.submit(
        "kaggle_import",
        lambda active: datasets.import_kaggle(body.slug, active),
        meta={"slug": body.slug, "preset": body.preset},
    )
    return {"job": job.as_dict(), "message": "Kaggle import started."}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = job_registry.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.as_dict()
