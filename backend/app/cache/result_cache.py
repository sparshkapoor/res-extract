import json
import shutil
from pathlib import Path

from app.config import get_settings
from app.db import get_db
from app.models import Recipe
from app.pipeline import normalize

# Bumped whenever a change to normalize.py (or a new Recipe/Ingredient field
# with a required backfill) means previously-cached recipes need
# reprocessing. 2 = normalize.py's deterministic ingredient/unit cleanup +
# Ingredient.note field. See get_cached()'s lazy self-heal below and
# scripts/repair_cache.py for the bulk equivalent.
RECIPE_SCHEMA_VERSION = 2


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
        # Prefer the dedicated hero shot (VLM-selected finished-dish frame,
        # independent of any step) over any step's own instructional frame —
        # matches the frontend's hero pick (RecipeCard.tsx). Falls back to the
        # last step's frame for recipes cached before hero_image_path existed.
        thumbnail = recipe.hero_image_path or next(
            (s.image_path for s in reversed(recipe.steps) if s.image_path), None
        )
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
            "SELECT recipe_json, schema_version FROM result_cache WHERE url_hash = ?", (url_hash,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        recipe = Recipe.model_validate_json(row["recipe_json"])

        if row["schema_version"] < RECIPE_SCHEMA_VERSION:
            # Lazy self-heal: a recipe cached under an older normalize.py
            # (or before a field like Ingredient.note existed) gets upgraded
            # in place on next read, so a cache hit is never stale even if
            # scripts/repair_cache.py was never run for this row. Cheap and
            # deterministic — no models involved.
            recipe = normalize.normalize_recipe(recipe)
            await db.execute(
                "UPDATE result_cache SET recipe_json = ?, schema_version = ? WHERE url_hash = ?",
                (recipe.model_dump_json(), RECIPE_SCHEMA_VERSION, url_hash),
            )
            await db.commit()

        return recipe


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
    if cached_recipe.hero_image_path:
        filename = Path(cached_recipe.hero_image_path).name
        cached_recipe.hero_image_path = f"/media/cache/{url_hash}/{filename}"

    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO result_cache (url_hash, url, recipe_json, media_dir, schema_version) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                url_hash,
                url,
                cached_recipe.model_dump_json(),
                str(media_dir.relative_to(settings.storage_dir)),
                RECIPE_SCHEMA_VERSION,
            ),
        )
        await db.commit()

    return media_dir
