import asyncio
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.models import Recipe

_WORKER_SCRIPT = Path(__file__).parent / "_vlm_worker.py"


class VlmError(RuntimeError):
    pass


def _needs_estimate(ingredient) -> bool:
    """The LLM's own `is_estimated` flag is unreliable — it sometimes leaves
    quantity/unit blank while still marking is_estimated=False. The
    objective signal is just: is there any quantity/unit text at all?"""
    return ingredient.is_estimated or not (ingredient.quantity or "").strip() and not (ingredient.unit or "").strip()


def _match_steps_to_ingredients(recipe: Recipe) -> list[dict]:
    """Associate each still-estimated ingredient with the first step whose
    instruction mentions it and that has an on-disk image — that's the
    frame the VLM should look at to refine the estimate."""
    requests = []
    for ingredient in recipe.ingredients:
        if not _needs_estimate(ingredient):
            continue  # already has a real, stated quantity — nothing to refine
        name_lower = ingredient.name.lower()
        for step in recipe.steps:
            if not step.image_path:
                continue
            if name_lower in step.instruction.lower():
                requests.append(
                    {
                        "id": ingredient.name,
                        "image_path": step.image_path,
                        "ingredient_name": ingredient.name,
                        "step_instruction": step.instruction,
                    }
                )
                break
    return requests


async def refine_estimates_with_vision(recipe: Recipe, job_frames_dir: Path) -> Recipe:
    """Runs Qwen2.5-VL over each still-estimated ingredient's associated
    step frame to ground the guess in what's actually visible, rather than
    text-only conventions. Falls back to the existing text estimate for any
    ingredient the VLM can't confidently parse a quantity for."""
    settings = get_settings()

    requests = _match_steps_to_ingredients(recipe)
    if not requests:
        return recipe

    # step.image_path is a `/media/jobs/{job_id}/...` URL — resolve it back
    # to the on-disk file the subprocess can actually read.
    for req in requests:
        req["image_path"] = str(job_frames_dir / Path(req["image_path"]).name)

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
        results = {r["id"]: r for r in json.loads(last_line)}
    except (IndexError, json.JSONDecodeError) as e:
        raise VlmError(f"Could not parse VLM worker output: {stdout.decode(errors='replace')[-2000:]}") from e

    for ingredient in recipe.ingredients:
        result = results.get(ingredient.name)
        if result and (result.get("quantity") or result.get("unit")):
            ingredient.quantity = result.get("quantity") or ingredient.quantity
            ingredient.unit = result.get("unit") or ingredient.unit
            ingredient.is_estimated = True  # vision-grounded, but still not a stated fact

    return recipe
