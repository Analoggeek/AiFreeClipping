"""Background job tracking + server-sent progress events."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Awaitable, Callable

from .db import db, dumps, now, uid


class JobManager:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def create(self, kind: str, payload: dict[str, Any] | None = None) -> str:
        job_id = uid("job_")
        db.insert(
            "jobs",
            {
                "id": job_id,
                "kind": kind,
                "status": "queued",
                "progress": 0,
                "message": "Queued",
                "payload": dumps(payload or {}),
                "result": None,
                "error": None,
                "created_at": now(),
                "updated_at": now(),
            },
        )
        return job_id

    def update(
        self,
        job_id: str,
        progress: float | None = None,
        message: str | None = None,
        *,
        status: str | None = None,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        values: dict[str, Any] = {"updated_at": now()}
        if progress is not None:
            values["progress"] = round(min(max(float(progress), 0), 100), 2)
        if message is not None:
            values["message"] = message
        if status is not None:
            values["status"] = status
        if result is not None:
            values["result"] = dumps(result)
        if error is not None:
            values["error"] = str(error)
        db.update("jobs", "id", job_id, values)
        event = {"job": self.get(job_id), "progress": progress, "message": message, "status": status}
        for queue in list(self._subscribers.get(job_id, set())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def get(self, job_id: str) -> dict[str, Any] | None:
        row = db.loads(db.one("SELECT * FROM jobs WHERE id=?", (job_id,)), "payload", "result")
        return row

    def list(self, limit: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs ORDER BY created_at DESC"
        rows = db.query(query, ()) if limit is None else db.query(f"{query} LIMIT ?", (limit,))
        return [db.loads(row, "payload", "result") for row in rows]

    def cancel(self, job_id: str) -> bool:
        """Cancel a live coroutine and mark its operation as cancelled."""
        job = self.get(job_id)
        if not job or job.get("status") not in {"queued", "running"}:
            return False
        task = self._tasks.get(job_id)
        if task and not task.done():
            # The HTTP handler can be called from a worker thread; wake the task's
            # loop safely instead of invoking Task.cancel() cross-thread.
            task.get_loop().call_soon_threadsafe(task.cancel)
        # Set the terminal state immediately, including the race where a task is
        # cancelled before its wrapper gets its first event-loop turn.
        self.update(job_id, status="cancelled", message="Cancelled by user")
        return True

    def subscribe(self, job_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.setdefault(job_id, set()).add(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        self._subscribers.get(job_id, set()).discard(queue)

    async def stream(self, job_id: str, heartbeat: float = 5.0) -> AsyncIterator[str]:
        queue = self.subscribe(job_id)
        try:
            job = self.get(job_id)
            if job:
                yield f"data: {json.dumps({'job': job})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                    if event.get("status") in ("done", "error", "cancelled"):
                        break
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            self.unsubscribe(job_id, queue)

    def run(self, kind: str, work: Callable[[str, Any], Awaitable[Any]], payload=None) -> str:
        """Create a job and execute `work(job_id, payload)` in the background."""
        job_id = self.create(kind, payload)

        async def wrapper() -> None:
            self.update(job_id, status="running", message="Starting…", progress=1)
            try:
                result = await work(job_id, payload)
                self.update(job_id, status="done", progress=100, message="Done", result=result or {})
            except asyncio.CancelledError:
                self.update(job_id, status="cancelled", message="Cancelled")
            except Exception as exc:  # surfaced in UI, never crashes the API
                self.update(job_id, status="error", message=str(exc), error=str(exc))

        task = asyncio.create_task(wrapper(), name=f"job-{job_id}")
        self._tasks[job_id] = task
        task.add_done_callback(lambda _task, key=job_id: self._tasks.pop(key, None))
        return job_id


jobs = JobManager()
