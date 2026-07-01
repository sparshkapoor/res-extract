from fastapi import APIRouter, HTTPException

from app.cache import result_cache
from app.jobs import job_manager
from app.models import JobStatus, Recipe, SavedRecipeSummary

router = APIRouter()


@router.get("/recipes", response_model=list[SavedRecipeSummary])
async def list_saved_recipes() -> list[SavedRecipeSummary]:
    return await result_cache.list_cached()


@router.get("/recipes/{url_hash}", response_model=Recipe)
async def get_saved_recipe(url_hash: str) -> Recipe:
    recipe = await result_cache.get_cached(url_hash)
    if recipe is None:
        raise HTTPException(status_code=404, detail="No saved recipe with that id")
    return recipe


@router.get("/jobs/{job_id}/result", response_model=Recipe)
async def get_job_result(job_id: str) -> Recipe:
    job = await job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    status = JobStatus(job["status"])
    if status != JobStatus.done:
        raise HTTPException(status_code=409, detail=f"Job not ready (status={status.value})")

    if not job["result_cache_id"]:
        raise HTTPException(status_code=500, detail="Job marked done but has no cached result")

    recipe = await result_cache.get_cached(job["result_cache_id"])
    if recipe is None:
        raise HTTPException(status_code=500, detail="Cached result missing")
    return recipe
