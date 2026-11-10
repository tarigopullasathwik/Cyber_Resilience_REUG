"""FastAPI entry point for EDGEGUARD AI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, settings
from .routers import datasets, ml, operations, ws


@asynccontextmanager
async def lifespan(application: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="EDGEGUARD AI",
    description=(
        "Adaptive edge cyber-resilience research platform: dataset management, leakage-safe "
        "preprocessing, model laboratory, unknown-attack evaluation, simulated containment, "
        "resource monitoring and experiment reporting."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc) or "File not found."})


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(datasets.router)
app.include_router(ml.router)
app.include_router(operations.router)
app.include_router(ws.router)


@app.get("/api")
def api_root() -> dict[str, str]:
    return {
        "service": "EDGEGUARD AI",
        "docs": "/docs",
        "health": "/api/health",
        "frontend": "/" if FRONTEND_DIST.exists() else "run the Vite dev server on port 5173",
    }


FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


class SPAStaticFiles(StaticFiles):
    """Serve the built SPA and fall back to index.html for client-side routes."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except Exception:
            return await super().get_response("index.html", scope)


if FRONTEND_DIST.exists():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
