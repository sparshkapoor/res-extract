import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.jobs import job_manager
from app.models import JobStatus, JobStatusResponse

router = APIRouter()

_TERMINAL_STATES = {JobStatus.done, JobStatus.failed}


def _sse_line(stage: str, status: str, message: str | None) -> str:
    data = json.dumps({"stage": stage, "status": status, "message": message})
    return f"event: progress\ndata: {data}\n\n"


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> JobStatusResponse:
    job = await job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job["job_id"],
        status=JobStatus(job["status"]),
        stage_message=job["stage_message"],
        error=job["error"],
        updated_at=job["updated_at"],
    )


@router.get("/jobs/{job_id}/events")
async def stream_job_events(job_id: str) -> StreamingResponse:
    job = await job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        current_status = JobStatus(job["status"])
        # If already terminal (e.g. cache hit, or client reconnected after
        # completion), emit a single final event and close immediately.
        if current_status in _TERMINAL_STATES:
            status_label = "success" if current_status == JobStatus.done else "failed"
            yield _sse_line(current_status.value, status_label, job["stage_message"] or job["error"])
            return

        queue = job_manager.subscribe(job_id)
        try:
            while True:
                event = await queue.get()
                yield _sse_line(event.stage.value, event.status, event.message)
                if event.stage in _TERMINAL_STATES:
                    break
        finally:
            job_manager.unsubscribe(job_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
