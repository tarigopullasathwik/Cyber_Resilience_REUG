"""API routes for containment, resources, analytics, reports, docs and the command center."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .. import jobs as job_registry
from .. import settings
from ..services import analytics, containment, datasets, docs, modeling, reports, resources

router = APIRouter(prefix="/api", tags=["operations"])


class SimulateRequest(BaseModel):
    experiment_id: str | None = None
    max_events: int = Field(default=8, ge=1, le=25)


class BudgetRequest(BaseModel):
    cpu_capacity: float | None = None
    memory_capacity_mb: float | None = None
    bandwidth_capacity_kbps: float | None = None
    detector_cpu_per_record: float | None = None
    memory_per_device_mb: float | None = None
    latency_budget_ms: float | None = None


class BenchmarkRequest(BaseModel):
    experiment_id: str
    sample_size: int = Field(default=120, ge=20, le=500)


class ReportRequest(BaseModel):
    experiment_id: str


@router.get("/containment/status")
def containment_status() -> dict[str, Any]:
    return containment.status()


@router.post("/containment/simulate", status_code=202)
def simulate_containment(body: SimulateRequest) -> dict[str, Any]:
    job = job_registry.jobs.submit(
        "containment",
        lambda active: containment.simulate(body.experiment_id, {"max_events": body.max_events}, active),
        meta={"experiment_id": body.experiment_id, "max_events": body.max_events},
    )
    return {"job": job.as_dict(), "message": "Containment replay started."}


@router.post("/containment/events/{event_id}/verify")
def verify_containment(event_id: str) -> dict[str, Any]:
    return containment.verify_event(event_id)


@router.post("/containment/events/{event_id}/release")
def release_containment(event_id: str) -> dict[str, Any]:
    return containment.release_event(event_id)


@router.get("/resources")
def resource_overview() -> dict[str, Any]:
    return resources.overview()


@router.patch("/resources/edge-budget")
def update_edge_budget(body: BudgetRequest) -> dict[str, Any]:
    budget = resources.set_budget(body.model_dump(exclude_none=True))
    return {"budget": budget, "edge": resources.edge_snapshot()}


@router.post("/resources/benchmark", status_code=202)
def benchmark_resources(body: BenchmarkRequest) -> dict[str, Any]:
    job = job_registry.jobs.submit(
        "resource_benchmark",
        lambda active: resources.benchmark(body.experiment_id, active, body.sample_size),
        meta={"experiment_id": body.experiment_id},
    )
    return {"job": job.as_dict(), "message": "Benchmark started."}


@router.get("/analytics/overview")
def analytics_overview() -> dict[str, Any]:
    return analytics.overview()


@router.get("/analytics/compare")
def analytics_compare(ids: str | None = None) -> dict[str, Any]:
    experiment_ids = [value for value in (ids or "").split(",") if value]
    return analytics.comparison(experiment_ids)


@router.get("/analytics/experiments/{experiment_id}")
def analytics_experiment(experiment_id: str) -> dict[str, Any]:
    return analytics.metric_series(experiment_id)


@router.get("/analytics/datasets")
def analytics_datasets() -> list[dict[str, Any]]:
    return analytics.dataset_usage()


@router.get("/analytics/export")
def analytics_export(
    experiment_id: str,
    format: Literal["csv", "json"] = Query(default="csv"),
) -> Response:
    if format == "csv":
        payload, filename = reports.export_csv(experiment_id)
        media = "text/csv"
    else:
        payload, filename = reports.export_json(experiment_id)
        media = "application/json"
    return Response(
        content=payload,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/threats")
def threat_intelligence(
    experiment_id: str | None = None,
    threshold: float = Query(default=0.5, ge=0.0, le=1.0),
) -> dict[str, Any]:
    return containment.threats(experiment_id, threshold)


@router.get("/command-center")
def command_center() -> dict[str, Any]:
    return analytics.overview()


@router.get("/reports")
def list_reports() -> list[dict[str, Any]]:
    return reports.list_reports()


@router.post("/reports", status_code=201)
def create_report(body: ReportRequest) -> dict[str, Any]:
    return reports.generate_pdf(body.experiment_id)


@router.get("/reports/{report_id}/download")
def download_report(report_id: str) -> FileResponse:
    path, title = reports.report_path(report_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{title.replace(' ', '_')}.pdf",
    )


@router.get("/documentation")
def documentation() -> dict[str, Any]:
    return docs.documentation()


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "EDGEGUARD AI",
        "research_title": settings.RESEARCH_TITLE,
        "scope": settings.SCOPE_NOTE,
        "kaggle": datasets.kaggle_status(),
        "models": [
            {"key": key, "label": spec["label"], "available": spec["available"]}
            for key, spec in modeling.MODEL_SPECS.items()
        ],
    }


@router.get("/jobs")
def list_jobs() -> list[dict[str, Any]]:
    return [job.as_dict() for job in job_registry.jobs.list()][:40]


@router.get("/model-artifact/{experiment_id}")
def model_artifact_info(experiment_id: str) -> dict[str, Any]:
    experiment = modeling.get_experiment(experiment_id)
    return {
        "experiment_id": experiment_id,
        "status": experiment["status"],
        "artifact_saved": experiment["artifact_saved"],
        "predictions_available": experiment["predictions_available"],
        "metrics": experiment["metrics"],
    }
