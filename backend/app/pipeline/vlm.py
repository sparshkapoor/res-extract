import asyncio
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.models import Ingredient, Recipe

_WORKER_SCRIPT = Path(__file__).parent / "_vlm_worker.py"

# Confidence tiers the "identify"/"hero" tasks can return — anything below
# this bar is treated the same as "unclear" (keep the generic name / fall
# back to the last-step image, don't guess).
_CONFIDENT = {"high", "medium"}
_CONFIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}


class VlmError(RuntimeError):
    pass


def _needs_estimate(ingredient) -> bool:
    """The LLM's own `is_estimated` flag is unreliable — it sometimes leaves
    quantity/unit blank while still marking is_estimated=False. The
    objective signal is just: is there any quantity/unit text at all?"""
    return ingredient.is_estimated or not (ingredient.quantity or "").strip() and not (ingredient.unit or "").strip()


def _find_matching_step_image(ingredient_name: str, recipe: Recipe) -> tuple[str, str] | None:
    """First step whose instruction mentions this ingredient name and that
    has an on-disk image — that's the frame the VLM should look at."""
    name_lower = ingredient_name.lower()
    for step in recipe.steps:
        if step.image_path and name_lower in step.instruction.lower():
            return step.image_path, step.instruction
    return None


def _match_steps_to_ingredients(recipe: Recipe) -> list[dict]:
    """Quantity-estimation requests for ingredients whose quantity/unit is
    still unknown."""
    requests = []
    for ingredient in recipe.ingredients:
        if not _needs_estimate(ingredient):
            continue  # already has a real, stated quantity — nothing to refine
        match = _find_matching_step_image(ingredient.name, recipe)
        if match is None:
            continue
        image_path, instruction = match
        requests.append(
            {
                "task": "quantity",
                "id": ingredient.name,
                "image_path": image_path,
                "ingredient_name": ingredient.name,
                "step_instruction": instruction,
            }
        )
    return requests


def _match_steps_to_generic_ingredients(recipe: Recipe) -> list[dict]:
    """Identify-task requests for ingredients whose *name* — not just
    quantity — is still a generic category (e.g. "spices"). This is the
    last-resort visual fallback: it only runs for ingredients still generic
    after the description-refinement and OCR-refinement passes have already
    had a chance to name them specifically (see orchestrator.py ordering)."""
    requests = []
    for ingredient in recipe.ingredients:
        if not ingredient.name_is_generic:
            continue
        match = _find_matching_step_image(ingredient.name, recipe)
        if match is None:
            continue
        image_path, instruction = match
        requests.append(
            {
                "task": "identify",
                # Ingredient names aren't guaranteed unique, but two generic
                # ingredients sharing one name would be a duplicate entry
                # anyway — use the object id to keep results unambiguous.
                "id": f"generic:{id(ingredient)}",
                "image_path": image_path,
                "ingredient_name": ingredient.name,
                "step_instruction": instruction,
            }
        )
    return requests


async def _call_worker(requests: list[dict]) -> dict[str, dict]:
    """Shared subprocess plumbing for every VLM task type. Returns results
    keyed by the request's `id`. Callers are responsible for `image_path`
    already being a real on-disk path — this function does no URL resolution
    of its own, since not every caller's paths need it (see
    refine_estimates_with_vision vs. caption_frame_action)."""
    settings = get_settings()

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(_WORKER_SCRIPT),
        settings.vlm_model_name,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(json.dumps(requests).encode())

    if proc.returncode != 0:
        raise VlmError(f"VLM subprocess failed: {stderr.decode(errors='replace')[-2000:]}")

    try:
        last_line = stdout.decode(errors="replace").strip().splitlines()[-1]
        return {r["id"]: r for r in json.loads(last_line)}
    except (IndexError, json.JSONDecodeError) as e:
        raise VlmError(f"Could not parse VLM worker output: {stdout.decode(errors='replace')[-2000:]}") from e


def _select_hero(hero_candidates: list[Path], results: dict[str, dict]) -> Path | None:
    """Picks the highest-confidence candidate the VLM marked as a genuine
    finished-dish shot. `None` means no candidate was confident — caller
    falls back to the existing last-step-image behavior rather than guess."""
    best_path: Path | None = None
    best_rank = -1
    for i, path in enumerate(hero_candidates):
        result = results.get(f"hero:{i}") or {}
        confidence_rank = _CONFIDENCE_RANK.get(result.get("confidence"), 0)
        if result.get("is_hero_shot") and confidence_rank > best_rank:
            best_rank, best_path = confidence_rank, path
    return best_path


def _split_generic_ingredient(ingredient: Ingredient, identified: list[str]) -> list[Ingredient]:
    """One generic ingredient -> N specifically-named ones. Still no real
    quantity per item (the VLM can guess *what*, not reliably *how much*),
    so each split entry keeps is_estimated=true and the same quantity/unit
    the original had (usually null -> renders as "to taste" in the UI)."""
    return [
        Ingredient(
            name=name,
            quantity=ingredient.quantity,
            unit=ingredient.unit,
            is_estimated=True,
            name_is_generic=False,
        )
        for name in identified
    ]


async def refine_estimates_with_vision(
    recipe: Recipe, job_frames_dir: Path, hero_candidates: list[Path] | None = None
) -> Recipe:
    """Runs Qwen2.5-VL over each still-estimated ingredient's associated step
    frame to ground the guess in what's actually visible (task="quantity"),
    separately over any ingredient whose *name* is still generic
    (task="identify") to try to name the specific spice/seasoning shown, and
    over a small set of dedicated hero-candidate frames (task="hero") to pick
    a clean finished-dish shot independent of any step. All task types are
    batched into the same subprocess call — one model load, not three. Now
    called unconditionally once per job (see orchestrator.py) since hero
    selection needs to run regardless of whether any ingredient needs
    refinement. Falls back to the existing text estimate / generic name /
    last-step image for anything the VLM can't confidently resolve."""
    quantity_requests = _match_steps_to_ingredients(recipe)
    identify_requests = _match_steps_to_generic_ingredients(recipe)

    # step.image_path is a `/media/jobs/{job_id}/...` URL — resolve it back
    # to the on-disk file the subprocess can actually read. Hero candidates
    # are already absolute on-disk paths (extracted directly, not tied to a
    # step), so they skip this resolution.
    for req in quantity_requests + identify_requests:
        req["image_path"] = str(job_frames_dir / Path(req["image_path"]).name)

    hero_requests = [
        {"task": "hero", "id": f"hero:{i}", "image_path": str(p)}
        for i, p in enumerate(hero_candidates or [])
    ]

    requests = quantity_requests + identify_requests + hero_requests
    if not requests:
        return recipe

    results = await _call_worker(requests)

    for ingredient in recipe.ingredients:
        result = results.get(ingredient.name)
        if result and (result.get("quantity") or result.get("unit")):
            ingredient.quantity = result.get("quantity") or ingredient.quantity
            ingredient.unit = result.get("unit") or ingredient.unit
            ingredient.is_estimated = True  # vision-grounded, but still not a stated fact

    if identify_requests:
        new_ingredients: list[Ingredient] = []
        for ingredient in recipe.ingredients:
            result = results.get(f"generic:{id(ingredient)}") if ingredient.name_is_generic else None
            identified = (result or {}).get("identified") or []
            confidence = (result or {}).get("confidence")
            if identified and confidence in _CONFIDENT:
                new_ingredients.extend(_split_generic_ingredient(ingredient, identified))
            else:
                # Unclear/low-confidence/no match — keep the clean generic
                # name as-is. This is the accepted fallback, not an error.
                new_ingredients.append(ingredient)
        recipe.ingredients = new_ingredients

    if hero_requests:
        best_path = _select_hero(hero_candidates or [], results)
        # Store the bare filename — orchestrator.py owns URL construction
        # (`/media/jobs/{job_id}/...`), same division of responsibility as
        # step.image_path. None means "no confident candidate": caller falls
        # back to the existing last-step-image behavior.
        recipe.hero_image_path = best_path.name if best_path else None

    return recipe


async def caption_frames(image_paths: list[Path]) -> dict[Path, str]:
    """Batched vision captioning for the silent-video narration fallback
    (vision_narration.py) — describes the cooking action in one imperative
    sentence per frame, or the food/ingredient shown if no action is visible.
    All frames go through ONE subprocess/model-load, not one per frame (an
    earlier version called the single-frame variant of this in a loop, which
    reloaded the VLM model from disk up to `vision_narration_max_frames`
    times per job). Missing entries in the returned dict mean the VLM
    produced nothing usable for that frame — callers treat that as
    contributing no narration rather than failing the whole pass."""
    if not image_paths:
        return {}
    requests = [
        {"task": "narrate", "id": f"narrate:{i}", "image_path": str(p)} for i, p in enumerate(image_paths)
    ]
    results = await _call_worker(requests)
    captions: dict[Path, str] = {}
    for i, path in enumerate(image_paths):
        caption = (results.get(f"narrate:{i}") or {}).get("caption", "")
        if caption:
            captions[path] = caption
    return captions
