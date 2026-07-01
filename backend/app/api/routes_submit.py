import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.cache import result_cache
from app.db import get_db
from app.jobs import job_manager
from app.models import JobCreateRequest, JobCreateResponse, JobStatus
from app.pipeline import orchestrator
from app.pipeline.url_utils import UnsupportedUrlError, detect_platform, normalize_url, sha256_of_url

router = APIRouter()


@router.post("/jobs", response_model=JobCreateResponse, status_code=202)
async def create_job(request: JobCreateRequest, background_tasks: BackgroundTasks) -> JobCreateResponse:
    url = normalize_url(request.url)
    try:
        platform = detect_platform(url)
    except UnsupportedUrlError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    url_hash = sha256_of_url(url)
    job_id = str(uuid.uuid4())

    cached_recipe = await result_cache.get_cached(url_hash)
    if cached_recipe is not None:
        await job_manager.create_job(job_id, url, url_hash, platform.value)
        async with get_db() as db:
            await db.execute(
                "UPDATE jobs SET status = ?, result_cache_id = ?, updated_at = datetime('now') WHERE job_id = ?",
                (JobStatus.done.value, url_hash, job_id),
            )
            await db.commit()
        return JobCreateResponse(job_id=job_id, status=JobStatus.done, cached=True)

    await job_manager.create_job(job_id, url, url_hash, platform.value)
    background_tasks.add_task(orchestrator.run_pipeline, job_id, url)
    return JobCreateResponse(job_id=job_id, status=JobStatus.queued, cached=False)
