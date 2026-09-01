from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from engine.app.core.db import utc_now


@dataclass
class JobRecord:
    id: str
    kind: str
    status: str = "pending"
    progress: float = 0.0
    message: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    subscribers: list[asyncio.Queue[dict[str, Any]]] = field(default_factory=list)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, kind: str) -> JobRecord:
        job_id = uuid.uuid4().hex
        job = JobRecord(id=job_id, kind=kind, status="pending")
        async with self._lock:
            self._jobs[job_id] = job
        return job

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def cancel(self, job_id: str) -> JobRecord | None:
        job = await self.get(job_id)
        if not job or job.status not in {"pending", "running"}:
            return None
        return await self.update(job_id, status="cancelled", message="Cancellation requested")

    async def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> JobRecord | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = max(0.0, min(100.0, progress))
            if message is not None:
                job.message = message
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            job.updated_at = utc_now()
            event = {
                "job_id": job.id,
                "status": job.status,
                "progress": job.progress,
                "message": job.message,
                "error": job.error,
                "updated_at": job.updated_at,
            }
            for queue in list(job.subscribers):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass
            return job

    async def subscribe(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        job = await self.get(job_id)
        if not job:
            raise KeyError(job_id)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        job.subscribers.append(queue)
        try:
            yield {
                "job_id": job.id,
                "status": job.status,
                "progress": job.progress,
                "message": job.message,
                "error": job.error,
                "updated_at": job.updated_at,
            }
            while job.status in {"pending", "running"}:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event
                except asyncio.TimeoutError:
                    yield {"job_id": job.id, "heartbeat": True, "updated_at": utc_now()}
        finally:
            if queue in job.subscribers:
                job.subscribers.remove(queue)

    def to_api(self, job: JobRecord) -> dict[str, Any]:
        return {
            "id": job.id,
            "kind": job.kind,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "result": job.result,
            "error": job.error,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }


job_manager = JobManager()
