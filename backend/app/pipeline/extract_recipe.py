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
typical SINGLE-COMPONENT recipe — a 30+ step list almost always means you've over-segmented into \
individual sentences instead of coherent cooking actions. EXCEPTION: if the recipe genuinely has multiple \
distinct components prepared somewhat independently (e.g. a sauce made alongside a main, a filling plus \
a dough, a garnish with its own prep), give each component's preparation its own step(s) even if that \
pushes the total past 15 — never merge away or silently drop a distinct sub-recipe just to stay under a \
step-count budget. The 5-15 guidance is about not over-segmenting a single thread of actions, not a cap \
on genuinely multi-part recipes.
- Each step's `verbatim_transcript_citation` MUST be an exact substring copied from the transcript text \
you were given — do not paraphrase it. This is used to map the step back to a timestamp, so it must be \
findable verbatim in the transcript.
- If a step involves a duration or temperature that matters for success (frying, baking, simmering, \
resting) and it was never stated in the video, estimate a typical, reasonable value for that specific \
food/technique from common cooking convention and state it naturally in the step's `instruction` text \
(e.g. "Fry until golden, about 3-4 minutes at 350°F"). Don't leave an execution-critical step vague \
just because a number wasn't spoken — apply the same judgment you already use to estimate ingredient \
quantities (see below), just expressed in the instruction text since steps have no separate \
estimated-quantity field.
- Fill `cook_time_minutes`, `servings`, `calories`, and `oven_temp_f` ONLY when the transcript or on-screen \
text states or clearly implies them (e.g. "bake for 25 minutes" -> cook_time_minutes could include that, \
"this makes 4 servings" -> servings=4, "preheat to 350" in an oven-baking context -> oven_temp_f=350). \
Leave any of these null rather than guessing — these top-level summary fields are not estimated, unlike \
the per-step duration/temperature guidance above (which is about instruction text, not these fields) or \
ingredient quantities.
- Normalize fractional/obscure measurements where possible (e.g. "a pinch of salt" stays as-is if no \
quantity was stated; "half a cup" becomes quantity="1/2", unit="cup").
- Do not invent ingredients or steps that aren't supported by the transcript.
- If an ingredient's quantity/unit is never stated (spoken or on-screen), estimate a reasonable typical \
amount for that ingredient in a dish like this, based on common recipe conventions (e.g. an unspecified \
"chicken thigh" in a stir-fry for ~2 servings might reasonably be "1 lb"; unspecified "salt" might be \
"1/2 tsp"). Set `is_estimated=true` on any ingredient whose quantity/unit you estimated this way, and \
`is_estimated=false` when the quantity/unit came directly from the transcript or on-screen text. Never \
mark a stated quantity as estimated, and never leave an estimate unmarked.
- If an ingredient is only ever referred to generically (e.g. "spices", "seasoning", "herbs") and never \
named specifically anywhere in the transcript, use the plain generic category word as `name` — e.g. \
name="spices" — and set `name_is_generic=true`. NEVER fabricate a parenthetical qualifier like "spices \
(not specified)" or "seasoning (unspecified)" as the name itself; the plain word plus the flag is the \
correct way to represent this. Set `name_is_generic=false` for every specifically-named ingredient.
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


def _build_description_prompt(ingredients_json: str, description_text: str) -> str:
    # Same "ingredients only, never touch steps" scoping as _build_pass2_prompt,
    # and the same reasoning applies: steps are already citation-grounded after
    # pass 1, and a video description has no timestamps to ground a step with.
    return (
        "Here are the ingredients already extracted from a video's spoken transcript:\n"
        f"{ingredients_json}\n\n"
        "Here is the video's own written description, straight from the creator "
        "(this is often MORE authoritative than the spoken transcript for exact "
        "ingredient names and quantities — creators write these down precisely, "
        "rather than saying them casually on camera):\n"
        f"{description_text}\n\n"
        "Revise the ingredients using the description as follows:\n"
        "- If the description states a more specific name or an exact quantity/unit for an "
        "ingredient that's currently estimated or generic, use the description's value and set "
        "is_estimated=false.\n"
        "- If a generic ingredient (name_is_generic=true, e.g. name=\"spices\") corresponds to an "
        "itemized breakdown in the description (e.g. \"Spices: 1 tsp salt, 1 tsp black pepper, "
        "1 tsp cinnamon\"), REPLACE that one generic ingredient with one Ingredient per item listed, "
        "each with its stated quantity/unit, is_estimated=false, and name_is_generic=false.\n"
        "- Never invent an ingredient that isn't in either the current list or the description.\n"
        "- Never delete an ingredient the description doesn't happen to mention — leave it as-is.\n"
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


async def refine_ingredients_with_description(
    ingredients: list[Ingredient], description_text: str
) -> list[Ingredient]:
    """Unlike refine_ingredients_with_ocr, this pass IS allowed to change the
    ingredient count — a generic ingredient (name_is_generic=true) can
    legitimately expand into several specific ones when the description
    itemizes it (e.g. "spices" -> salt/pepper/cumin/paprika/... each with a
    real stated quantity). No alignment-by-index safety net here since the
    count is expected to change; the prompt itself is the guardrail (never
    invent items absent from both sources, never drop unmentioned ones)."""
    ingredients_json = _IngredientsOnly(ingredients=ingredients).model_dump_json()
    prompt = _build_description_prompt(ingredients_json, description_text)
    raw = await asyncio.to_thread(_chat_sync, prompt, _IngredientsOnly)
    refined = _IngredientsOnly.model_validate(raw)

    if not refined.ingredients:
        # The model returned nothing usable — keep the originals rather than
        # silently emptying the ingredient list.
        return ingredients
    return refined.ingredients
