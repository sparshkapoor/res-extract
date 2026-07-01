import asyncio
import json

import ollama
from pydantic import BaseModel

from app.config import get_settings
from app.models import Ingredient, Platform, Recipe, Step


class _IngredientsOnly(BaseModel):
    ingredients: list[Ingredient]


class _StepInstruction(BaseModel):
    index: int
    instruction: str


class _InstructionsOnly(BaseModel):
    steps: list[_StepInstruction]


_SYSTEM_PROMPT = """You are a culinary transcript parser. You extract structured recipes from noisy, \
colloquial cooking-video transcripts. Represent the recipe as an imperative "program": a title, a list \
of ingredients with normalized quantities/units, and an ordered list of steps where each step is a \
single imperative action (e.g. "Melt butter in a pan over medium heat.").

Rules:
- Output must conform exactly to the given JSON schema.
- Group related consecutive actions into ONE step rather than one step per sentence (e.g. "add flour,\
sugar, and salt to a bowl and whisk together" is one step, not three). Aim for roughly 5-15 steps for a \
typical recipe — a 30+ step list almost always means you've over-segmented into individual sentences \
instead of coherent cooking actions.
- Each step's `verbatim_transcript_citation` MUST be an exact substring copied from the transcript text \
you were given — do not paraphrase it. This is used to map the step back to a timestamp, so it must be \
findable verbatim in the transcript.
- Normalize fractional/obscure measurements where possible (e.g. "a pinch of salt" stays as-is if no \
quantity was stated; "half a cup" becomes quantity="1/2", unit="cup").
- Do not invent ingredients or steps that aren't supported by the transcript.
- If an ingredient's quantity/unit is never stated (spoken or on-screen), estimate a reasonable typical \
amount for that ingredient in a dish like this, based on common recipe conventions (e.g. an unspecified \
"chicken thigh" in a stir-fry for ~2 servings might reasonably be "1 lb"; unspecified "salt" might be \
"1/2 tsp"). Set `is_estimated=true` on any ingredient whose quantity/unit you estimated this way, and \
`is_estimated=false` when the quantity/unit came directly from the transcript or on-screen text. Never \
mark a stated quantity as estimated, and never leave an estimate unmarked.
"""


def _build_pass1_prompt(transcript_text: str, source_url: str, platform: Platform) -> str:
    return (
        f"Source URL: {source_url}\n"
        f"Platform: {platform.value}\n\n"
        f"Transcript:\n{transcript_text}\n\n"
        "Extract the recipe as a JSON object matching the schema."
    )


def _build_pass2_prompt(ingredients_json: str, ocr_text: str) -> str:
    # Deliberately scoped to ingredients ONLY — this pass never sees or
    # touches steps. An earlier version asked the model to re-emit the full
    # recipe (steps included), and on longer/more complex recipes (~30
    # steps) it would silently reorder or duplicate step text relative to
    # its citation, since nothing forced the rewritten list to stay aligned
    # with the original. Steps are already correct after pass 1 + citation
    # mapping; there's no reason for on-screen ingredient text to ever
    # trigger a step rewrite.
    return (
        "Here are the ingredients already extracted from a video's spoken transcript:\n"
        f"{ingredients_json}\n\n"
        "Here is deduplicated on-screen text captured via OCR from the video's frames "
        "(this often contains measurements or ingredients that were shown but never said aloud):\n"
        f"{ocr_text}\n\n"
        "Revise ONLY the quantities/units that the OCR text conflicts with or adds information beyond "
        "the transcript. If OCR gives you a real quantity for an ingredient that was previously estimated, "
        "set is_estimated=false for it. Keep every ingredient name and count exactly the same — do not "
        "add, remove, or reorder ingredients. "
        "Output the full revised ingredients list as a JSON object matching the schema."
    )


def _build_proofread_prompt(steps_json: str) -> str:
    return (
        "Here are recipe steps extracted from a video transcript, each with its index, its current "
        "instruction text, and the exact transcript sentence it was derived from:\n"
        f"{steps_json}\n\n"
        "Proofread ONLY the `instruction` field of each step. Fix instructions that are garbled, "
        "truncated, non-English gibberish, or don't logically match their citation — rewrite them as a "
        "clean imperative sentence that faithfully reflects the citation. If an instruction is already "
        "clear and matches its citation, leave it completely unchanged. Do not add, remove, or reorder "
        "steps, and keep every `index` exactly as given. "
        "Output the full list as a JSON object matching the schema."
    )


def _client() -> ollama.Client:
    settings = get_settings()
    return ollama.Client(host=settings.ollama_host)


def _chat_sync(prompt: str, schema: type[BaseModel]) -> dict:
    settings = get_settings()
    client = _client()
    response = client.chat(
        model=settings.ollama_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        format=schema.model_json_schema(),
        keep_alive=settings.ollama_keep_alive,
        options={"temperature": 0.1, "num_ctx": settings.ollama_num_ctx},
    )
    return json.loads(response["message"]["content"])


async def call_llm(transcript_text: str, source_url: str, platform: Platform) -> Recipe:
    prompt = _build_pass1_prompt(transcript_text, source_url, platform)
    raw = await asyncio.to_thread(_chat_sync, prompt, Recipe)
    recipe = Recipe.model_validate(raw)
    recipe.source_url = source_url
    recipe.platform = platform
    return recipe


async def proofread_steps(steps: list[Step]) -> list[Step]:
    """Defense-in-depth against LLM output degradation on longer/more
    complex recipes (observed: garbled fragments like 'My macaroas' on a
    30-step extraction). Reviews instruction text against its own citation
    and fixes anything garbled — never touches citation/timestamp/image."""
    # Citations are included as read-only context so the model can judge
    # whether an instruction actually matches what was said, without a
    # schema field for them (so it has no way to "fix" a citation instead).
    context = [
        {"index": s.index, "instruction": s.instruction, "citation": s.verbatim_transcript_citation}
        for s in steps
    ]
    prompt = _build_proofread_prompt(json.dumps(context))
    raw = await asyncio.to_thread(_chat_sync, prompt, _InstructionsOnly)
    proofed = _InstructionsOnly.model_validate(raw)

    if len(proofed.steps) != len(steps) or {s.index for s in proofed.steps} != {s.index for s in steps}:
        # Same alignment safety as refine_ingredients_with_ocr — if the
        # index set doesn't match exactly, don't risk misapplying corrections.
        return steps

    fixed_by_index = {s.index: s.instruction for s in proofed.steps}
    for step in steps:
        step.instruction = fixed_by_index[step.index]
    return steps


async def refine_ingredients_with_ocr(ingredients: list[Ingredient], ocr_text: str) -> list[Ingredient]:
    ingredients_json = _IngredientsOnly(ingredients=ingredients).model_dump_json()
    prompt = _build_pass2_prompt(ingredients_json, ocr_text)
    raw = await asyncio.to_thread(_chat_sync, prompt, _IngredientsOnly)
    refined = _IngredientsOnly.model_validate(raw)

    if len(refined.ingredients) != len(ingredients):
        # The model didn't follow the "don't add/remove ingredients"
        # instruction — can't trust the alignment, so keep the originals
        # rather than risk silently dropping or duplicating an ingredient.
        return ingredients
    return refined.ingredients
