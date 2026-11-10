"""WebSocket progress channel for background jobs."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..jobs import jobs

router = APIRouter()

TERMINAL = {"completed", "failed"}


@router.websocket("/ws/jobs/{job_id}")
async def job_progress(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            job = jobs.get(job_id)
            if not job:
                await websocket.send_json({"error": "Job not found", "id": job_id})
                break
            await websocket.send_json(job.as_dict())
            if job.status in TERMINAL:
                break
            await asyncio.sleep(0.35)
    except WebSocketDisconnect:
        return
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass
