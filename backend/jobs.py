"""Background job registry with progress reporting.

Long-running work (dataset import, preprocessing, training, LOFO evaluation,
containment replay) runs in a small thread pool. A job exposes a monotonically
increasing progress value and a human-readable message which the browser reads
through a WebSocket (falling back to polling).
"""

from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from . import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued"
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    meta: dict[str, Any] = field(default_factory=dict)

    def update(self, progress: float | None = None, message: str | None = None) -> None:
        if progress is not None:
            self.progress = max(0.0, min(1.0, float(progress)))
        if message is not None:
            self.message = message
        self.updated_at = _now()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 4),
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "meta": self.meta,
        }


ProgressFn = Callable[[float, str], None]


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="edgeguard-job")

    def _register(self, kind: str, meta: dict[str, Any] | None) -> Job:
        job = Job(id=uuid.uuid4().hex[:16], kind=kind, meta=meta or {})
        with self._lock:
            self._jobs[job.id] = job
        return job

    def submit(self, kind: str, fn: Callable[[Job], Any], meta: dict[str, Any] | None = None) -> Job:
        job = self._register(kind, meta)
        if settings.SYNC_JOBS:
            self._run(job, fn)
        else:
            self._executor.submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: Callable[[Job], Any]) -> None:
        job.status = "running"
        job.update(0.01, "Starting")
        try:
            result = fn(job)
            job.result = result
            job.status = "completed"
            job.update(1.0, "Completed")
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI with a traceback tail
            job.status = "failed"
            job.error = str(exc)
            job.message = f"Failed: {exc}"
            job.updated_at = _now()
            job.meta["traceback"] = traceback.format_exc()[-4000:]
        finally:
            job.updated_at = _now()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())


jobs = JobManager()
