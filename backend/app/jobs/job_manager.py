import asyncio
import time
from typing import Any

from app.db import get_db
from app.models import JobEvent, JobStatus

# Per-job SSE broadcast queues. Purely in-memory and best-effort: SQLite
# (jobs + job_events tables) remains the source of truth for state, so a
# server restart or a dropped SSE connection never loses progress — a
# reconnecting client just falls back to polling GET /api/jobs/{id}.
_subscribers: dict[str, list[asyncio.Queue[JobEvent]]] = {}


async def create_job(job_id: str, url: str, url_hash: str, platform: str) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO jobs (job_id, url, url_hash, platform, status) VALUES (?, ?, ?, ?, ?)",
            (job_id, url, url_hash, platform, JobStatus.queued.value),
        )
        await db.commit()


async def update_status(
    job_id: str,
    status: JobStatus,
    message: str | None = None,
    error: str | None = None,
) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE jobs SET status = ?, stage_message = ?, error = ?, updated_at = datetime('now') "
            "WHERE job_id = ?",
            (status.value, message, error, job_id),
        )
        event_status = "failed" if status == JobStatus.failed else (
            "success" if status == JobStatus.done else "in_progress"
        )
        await db.execute(
            "INSERT INTO job_events (job_id, stage, status, message) VALUES (?, ?, ?, ?)",
            (job_id, status.value, event_status, message or error),
        )
        await db.commit()

    event = JobEvent(stage=status, status=event_status, message=message or error, ts=time.time())
    for queue in _subscribers.get(job_id, []):
        await queue.put(event)


async def get_job(job_id: str) -> dict[str, Any] | None:
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


def subscribe(job_id: str) -> asyncio.Queue[JobEvent]:
    queue: asyncio.Queue[JobEvent] = asyncio.Queue()
    _subscribers.setdefault(job_id, []).append(queue)
    return queue


def unsubscribe(job_id: str, queue: asyncio.Queue[JobEvent]) -> None:
    subs = _subscribers.get(job_id, [])
    if queue in subs:
        subs.remove(queue)
    if not subs:
        _subscribers.pop(job_id, None)
