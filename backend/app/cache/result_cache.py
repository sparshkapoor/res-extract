import json
import shutil
from pathlib import Path

from app.config import get_settings
from app.db import get_db
from app.models import Recipe


async def list_cached() -> list[dict]:
    """Lightweight metadata for every recipe ever extracted — the "Saved
    Recipes" gallery. Kept separate from get_cached() since a listing view
    shouldn't pay to parse+return the full steps/ingredients payload for
    every row."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT url_hash, url, recipe_json, created_at FROM result_cache ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        recipe = Recipe.model_validate_json(row["recipe_json"])
        # Last available frame, not first — matches the frontend's hero pick
        # (RecipeCard.tsx) so the grid thumbnail and the detail-view hero show
        # the same frame for a given recipe.
        thumbnail = next((s.image_path for s in reversed(recipe.steps) if s.image_path), None)
        results.append(
            {
                "url_hash": row["url_hash"],
                "url": row["url"],
                "title": recipe.title,
                "platform": recipe.platform,
                "thumbnail": thumbnail,
                "created_at": row["created_at"],
            }
        )
    return results


async def get_cached(url_hash: str) -> Recipe | None:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT recipe_json FROM result_cache WHERE url_hash = ?", (url_hash,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Recipe.model_validate_json(row["recipe_json"])


async def write_cache(url_hash: str, url: str, recipe: Recipe, job_frames_dir: Path) -> Path:
    settings = get_settings()
    media_dir = settings.cache_dir / url_hash
    media_dir.mkdir(parents=True, exist_ok=True)

    if job_frames_dir.exists():
        for frame in job_frames_dir.glob("*.jpg"):
            shutil.copy2(frame, media_dir / frame.name)

    # Rewrite image_path fields to point at the persistent cache location
    # rather than the (potentially cleaned up) per-job storage dir.
    cached_recipe = recipe.model_copy(deep=True)
    for step in cached_recipe.steps:
        if step.image_path:
            filename = Path(step.image_path).name
            step.image_path = f"/media/cache/{url_hash}/{filename}"

    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO result_cache (url_hash, url, recipe_json, media_dir) VALUES (?, ?, ?, ?)",
            (url_hash, url, cached_recipe.model_dump_json(), str(media_dir.relative_to(settings.storage_dir))),
        )
        await db.commit()

    return media_dir
