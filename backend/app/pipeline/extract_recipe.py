import asyncio
import json
from typing import Callable, Literal

import ollama
from pydantic import BaseModel

from app.config import get_settings
from app.models import Ingredient, Platform, Recipe, Step
from app.pipeline.normalize import CANONICAL_UNIT_TOKENS
from app.pipeline.transcript import estimate_tokens


class _IngredientsOnly(BaseModel):
    ingredients: list[Ingredient]


class _StepInstruction(BaseModel):
    index: int
    instruction: str


class _InstructionsOnly(BaseModel):
    steps: list[_StepInstruction]


class _CommentConfidence(BaseModel):
    confidence: Literal["high", "medium", "low"]
    matches_dish: bool


# Reused verbatim from normalize.py so the prompt can never list a unit the
# normalizer doesn't also recognize (and vice versa).
_UNIT_GLOSSARY = ", ".join(CANONICAL_UNIT_TOKENS)

_SYSTEM_PASS1 = f"""You are a culinary transcript parser. You extract structured recipes from noisy, \
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
- One coherent action per step — never collapse the whole recipe into a single step like "mix all the \
ingredients". Name the specific ingredients being combined or acted on in each step. Include technique \
and doneness cues (temperature, time, visual/textural sign of doneness) when the narration or on-screen \
text states them. A short video is not an excuse for a terse recipe — it still gets one step per distinct \
action, just as a longer video would.
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
- `unit` must be one of these canonical tokens, or null: {_UNIT_GLOSSARY}. Never put a free-text note \
(e.g. "for heating the pan", "(optional)"), a preposition phrase, or a number in `unit` — put a number \
that belongs with the unit into `quantity` instead, and anything else into a separate note if the schema \
has one; otherwise just omit it.
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

# Refine passes (OCR-text and description-text ingredient refinement) never
# touch steps and never need the full extraction ruleset above — sending the
# ~50-line pass-1 prompt on every one of these smaller calls was pure waste.
# NOTE: an earlier, shorter version of this prompt dropped the "copy concrete
# values in" rule below and measurably regressed quality — live-eval testing
# on the rye-pitas golden case showed the model would leave an ingredient at
# quantity=null/is_estimated=true even when the description stated an exact
# amount for it (e.g. "1 lb ground beef" never landing in the output). The
# task-specific instructions in _build_description_prompt/_build_pass2_prompt
# alone were not enough to reproduce the old full-prompt behavior.
_SYSTEM_INGREDIENT_REFINE = f"""You are revising a recipe's ingredient list using one additional source \
of text. Output must conform exactly to the given JSON schema. `unit` must be one of these canonical \
tokens, or null: {_UNIT_GLOSSARY} — never a free-text note, a preposition phrase, or a number. If the \
source text states a concrete quantity/unit for an ingredient that was previously null or estimated, you \
MUST copy that concrete value into quantity/unit and set is_estimated=false — never leave quantity=null \
once a real value is available in the text you were given. Follow the specific revision instructions in \
the user message exactly, and change nothing they don't ask you to change."""

_SYSTEM_PROOFREAD = """You are proofreading recipe step instructions against the transcript citation each \
was derived from. Output must conform exactly to the given JSON schema. Fix only instructions that are \
garbled, truncated, non-English gibberish, or don't logically match their citation; leave every other \
instruction completely unchanged. Never add, remove, or reorder steps, and keep every `index` exactly as \
given."""

# WS4d — comment-mining. A viewer's comment can state a concrete quantity a
# no-narration video never does, but it's still an UNVERIFIED external
# claim (a fan's guess at a recreation, not the creator's own numbers) —
# never treated as authoritative the way the transcript/description/OCR
# passes are. Two separate calls, deliberately: one judges dish-identity
# plausibility only (never asked to verify quantities — that's not
# verifiable from a transcript/frames), the other actually fills values,
# and always keeps is_estimated=true + a provenance note rather than the
# refine-pass norm of is_estimated=false, so the UI's "not stated in the
# video" framing (RecipeCard.tsx) stays accurate for values sourced here.
_SYSTEM_COMMENT_CONFIDENCE = """You judge whether a YouTube comment plausibly describes the SAME dish as a \
recipe extracted from a cooking video's transcript — NOT whether the comment's numbers are correct; you have \
no way to verify quantities from a transcript alone and must never claim to. Compare the comment's \
ingredients against the video's transcript and its already-extracted ingredient list. Recognize garbled \
transcript variants of the same word (e.g. transcript "go jang" is the same ingredient as a comment's \
"gochujang"). Set matches_dish=true only if the comment's ingredients substantially overlap with the dish \
actually being made — not a different recipe, not pure banter/reaction with no real ingredient list. Set \
confidence="high" only when matches_dish=true AND the comment reads as a genuine, specific recreation \
(concrete quantities/units for most of its ingredients), not a vague guess, a joke, or one ingredient \
mentioned in passing. Use "medium" for a plausible but incomplete or less certain match, and "low" for \
anything that doesn't clearly describe this dish. Output must conform exactly to the given JSON schema."""

_SYSTEM_COMMENT_REFINE = f"""You are revising a recipe's ingredient list using a comment left by a viewer of \
the video, who appears to describe their own recreation of this dish. Output must conform exactly to the \
given JSON schema. `unit` must be one of these canonical tokens, or null: {_UNIT_GLOSSARY} — never a \
free-text note, a preposition phrase, or a number. If the comment states a concrete quantity/unit for an \
ingredient that is currently null or estimated, copy that value into quantity/unit — but this value was NOT \
stated in the video itself, so you MUST leave is_estimated=true (never set it false from this source) and \
set `note` to "from a viewer's comment" (append with "; " if the ingredient already has a note) so this \
value is never confused with something the video itself stated. Follow the specific revision instructions \
in the user message exactly, and change nothing they don't ask you to change."""


# One few-shot example, as a user/assistant message pair ahead of the real
# pass-1 prompt. A short, sparsely-narrated recipe on purpose — this is
# exactly the failure class users reported (short videos collapsing into one
# terse step) — demonstrating correct decomposition into distinct steps,
# verbatim citations, canonical units, and both is_estimated states. Exactly
# one example: small instruction-tuned models degrade with long multi-shot
# prompts, and one clear example is enough to anchor the output shape.
_FEW_SHOT_TRANSCRIPT = (
    "Okay so today I'm making a quick garlic butter sauce. First melt a stick of butter in a pan over "
    "medium heat. Once it's melted, add in like four cloves of minced garlic and cook until fragrant, "
    "maybe thirty seconds. Then squeeze in the juice of one lemon and a splash of white wine, let it "
    "simmer for two minutes. Take it off the heat and stir in some chopped parsley and a pinch of salt. "
    "That's it, drizzle it over your fish or pasta."
)

_FEW_SHOT_RECIPE = {
    "title": "Quick Garlic Butter Sauce",
    "source_url": "https://example.com/demo-video",
    "platform": "youtube",
    "ingredients": [
        {"name": "butter", "quantity": "1", "unit": "stick", "is_estimated": False,
         "name_is_generic": False, "note": None},
        {"name": "garlic", "quantity": "4", "unit": "clove", "is_estimated": False,
         "name_is_generic": False, "note": None},
        {"name": "lemon juice", "quantity": "1", "unit": None, "is_estimated": False,
         "name_is_generic": False, "note": "juice of one lemon"},
        {"name": "white wine", "quantity": "2", "unit": "tbsp", "is_estimated": True,
         "name_is_generic": False, "note": None},
        {"name": "parsley", "quantity": "1", "unit": "tbsp", "is_estimated": True,
         "name_is_generic": False, "note": "chopped"},
        {"name": "salt", "quantity": None, "unit": "pinch", "is_estimated": False,
         "name_is_generic": False, "note": None},
    ],
    "steps": [
        {"index": 0, "instruction": "Melt butter in a pan over medium heat.",
         "verbatim_transcript_citation": "melt a stick of butter in a pan over medium heat",
         "timestamp_seconds": None, "image_path": None},
        {"index": 1, "instruction": "Add minced garlic and cook until fragrant, about 30 seconds.",
         "verbatim_transcript_citation": "add in like four cloves of minced garlic and cook until "
         "fragrant, maybe thirty seconds", "timestamp_seconds": None, "image_path": None},
        {"index": 2, "instruction": "Squeeze in lemon juice and white wine, and simmer for 2 minutes.",
         "verbatim_transcript_citation": "squeeze in the juice of one lemon and a splash of white wine, "
         "let it simmer for two minutes", "timestamp_seconds": None, "image_path": None},
        {"index": 3, "instruction": "Remove from heat and stir in chopped parsley and a pinch of salt.",
         "verbatim_transcript_citation": "take it off the heat and stir in some chopped parsley and a "
         "pinch of salt", "timestamp_seconds": None, "image_path": None},
        {"index": 4, "instruction": "Drizzle the sauce over fish or pasta to serve.",
         "verbatim_transcript_citation": "drizzle it over your fish or pasta",
         "timestamp_seconds": None, "image_path": None},
    ],
    "hero_image_path": None,
    "cook_time_minutes": 5,
    "servings": None,
    "calories": None,
    "oven_temp_f": None,
}


def _build_pass1_prompt(
    transcript_text: str, source_url: str, platform: Platform, corrective_note: str | None = None
) -> str:
    prompt = (
        f"Source URL: {source_url}\n"
        f"Platform: {platform.value}\n\n"
        f"Transcript:\n{transcript_text}\n\n"
        "Extract the recipe as a JSON object matching the schema."
    )
    if corrective_note:
        # Appended by orchestrator.py's bounded retry when validate.py flags
        # too-few/terse steps on the first attempt — built from that
        # attempt's specific findings, not a generic nudge.
        prompt += f"\n\n{corrective_note}"
    return prompt


_FEW_SHOT_MESSAGES = [
    {
        "role": "user",
        "content": _build_pass1_prompt(_FEW_SHOT_TRANSCRIPT, "https://example.com/demo-video", Platform.youtube),
    },
    {"role": "assistant", "content": json.dumps(_FEW_SHOT_RECIPE)},
]

# Every pass-1 call pays this fixed cost (system prompt + few-shot example)
# before a single token of the real transcript is counted. Exposed so
# orchestrator.py can compute how much of num_ctx is actually left for the
# transcript itself when deciding whether to truncate (see
# transcript.budget_segments).
PASS1_PROMPT_OVERHEAD_TOKENS = estimate_tokens(
    _SYSTEM_PASS1 + "".join(m["content"] for m in _FEW_SHOT_MESSAGES)
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
        "1 tsp cinnamon\"), REPLACE that one generic ingredient with one Ingredient per item listed. "
        "The SPECIFIC INGREDIENT WORD goes in `name`, never in `quantity`. For the example above, "
        "output exactly: {\"name\": \"salt\", \"quantity\": \"1\", \"unit\": \"tsp\", \"is_estimated\": "
        "false, \"name_is_generic\": false} — NOT {\"name\": \"spices\", \"quantity\": \"1 tsp salt\", "
        "...}. `name` must never be the literal word \"spices\"/\"seasoning\"/\"herbs\" once you have a "
        "specific breakdown to work from — that generic word's only valid use is when NO breakdown "
        "exists anywhere.\n"
        "- Never invent an ingredient that isn't in either the current list or the description.\n"
        "- Never delete an ingredient the description doesn't happen to mention — leave it as-is.\n"
        "Output the full revised ingredients list as a JSON object matching the schema."
    )


def _build_comment_confidence_prompt(transcript_text: str, ingredients_json: str, comment_text: str) -> str:
    return (
        f"Video transcript:\n{transcript_text}\n\n"
        f"Ingredients already extracted from the transcript:\n{ingredients_json}\n\n"
        f"Candidate viewer comment:\n{comment_text}\n\n"
        "Rate this comment as described in your instructions."
    )


def _build_comment_refine_prompt(ingredients_json: str, comment_text: str) -> str:
    return (
        "Here are the ingredients already extracted from a video's spoken transcript:\n"
        f"{ingredients_json}\n\n"
        "Here is a comment left by a viewer of the video, already judged to plausibly describe their own "
        "recreation of this same dish (this is an unverified external claim, not something the video itself "
        "stated):\n"
        f"{comment_text}\n\n"
        "Revise ONLY ingredients that are currently is_estimated=true or have quantity=null, and only when "
        "this comment states a concrete quantity/unit for that SAME ingredient (match by meaning, not exact "
        "spelling — e.g. 'gochujang' matches an ASR-garbled transcript ingredient named 'go jang'). Never "
        "invent an ingredient not already in the list, never delete one, and keep every ingredient name and "
        "count exactly the same. For every ingredient you fill in, keep is_estimated=true and add the "
        "provenance note exactly as instructed. "
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


def _chat_sync(prompt: str, schema: type[BaseModel], system: str, few_shot: list[dict] | None = None) -> dict:
    settings = get_settings()
    client = _client()
    messages = [{"role": "system", "content": system}]
    if few_shot:
        messages.extend(few_shot)
    messages.append({"role": "user", "content": prompt})
    response = client.chat(
        model=settings.ollama_model,
        messages=messages,
        format=schema.model_json_schema(),
        keep_alive=settings.ollama_keep_alive,
        options={"temperature": settings.llm_temperature, "num_ctx": settings.ollama_num_ctx},
        # Qwen3-family models default to emitting a hidden chain-of-thought
        # ("thinking") pass before the actual response — 10x+ slower and
        # pointless for JSON-constrained extraction where we only want the
        # schema-conforming answer. Harmless no-op on non-thinking models
        # like qwen2.5 (confirmed: identical output, ignored silently).
        think=False,
    )
    return json.loads(response["message"]["content"])


async def _chat(prompt: str, schema: type[BaseModel], system: str, few_shot: list[dict] | None = None) -> BaseModel:
    raw = await asyncio.to_thread(_chat_sync, prompt, schema, system, few_shot)
    return schema.model_validate(raw)


async def _chat_with_retry(
    prompt: str,
    schema: type[BaseModel],
    system: str,
    is_valid: Callable[[BaseModel], bool],
    corrective_note: str,
) -> tuple[BaseModel, bool]:
    """One bounded retry when the model doesn't follow the alignment
    contract (wrong count, wrong index set) refine/proofread calls depend
    on. Most mismatches are one-off sampling noise, not the model refusing
    the instruction, so a single corrective nudge recovers a useful result
    far more often than immediately discarding the whole call."""
    parsed = await _chat(prompt, schema, system, few_shot=None)
    if is_valid(parsed):
        return parsed, True
    retried = await _chat(f"{prompt}\n\n{corrective_note}", schema, system, few_shot=None)
    return retried, is_valid(retried)


async def call_llm(
    transcript_text: str, source_url: str, platform: Platform, corrective_note: str | None = None
) -> Recipe:
    prompt = _build_pass1_prompt(transcript_text, source_url, platform, corrective_note)
    recipe = await _chat(prompt, Recipe, _SYSTEM_PASS1, few_shot=_FEW_SHOT_MESSAGES)
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
    expected_indexes = {s.index for s in steps}

    def is_valid(parsed: _InstructionsOnly) -> bool:
        return len(parsed.steps) == len(steps) and {s.index for s in parsed.steps} == expected_indexes

    proofed, ok = await _chat_with_retry(
        prompt,
        _InstructionsOnly,
        _SYSTEM_PROOFREAD,
        is_valid,
        f"Your previous response did not return exactly one instruction for each of these step indexes, "
        f"unchanged: {sorted(expected_indexes)}. Return exactly that set of indexes, no more, no fewer.",
    )
    if not ok:
        # Same alignment safety as refine_ingredients_with_ocr — if the
        # index set still doesn't match exactly after the retry, don't risk
        # misapplying corrections.
        return steps

    fixed_by_index = {s.index: s.instruction for s in proofed.steps}
    for step in steps:
        step.instruction = fixed_by_index[step.index]
    return steps


async def refine_ingredients_with_ocr(ingredients: list[Ingredient], ocr_text: str) -> list[Ingredient]:
    ingredients_json = _IngredientsOnly(ingredients=ingredients).model_dump_json()
    prompt = _build_pass2_prompt(ingredients_json, ocr_text)
    want = len(ingredients)

    def is_valid(parsed: _IngredientsOnly) -> bool:
        return len(parsed.ingredients) == want

    refined, ok = await _chat_with_retry(
        prompt,
        _IngredientsOnly,
        _SYSTEM_INGREDIENT_REFINE,
        is_valid,
        f"Your previous response changed the ingredient count. Return exactly {want} ingredients — the "
        "same ones, in the same order — revising only their quantity/unit/is_estimated fields.",
    )
    if not ok:
        # The model didn't follow the "don't add/remove ingredients"
        # instruction even after a corrective retry — can't trust the
        # alignment, so keep the originals rather than risk silently
        # dropping or duplicating an ingredient.
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
    refined = await _chat(prompt, _IngredientsOnly, _SYSTEM_INGREDIENT_REFINE)

    if not refined.ingredients:
        # The model returned nothing usable — keep the originals rather than
        # silently emptying the ingredient list.
        return ingredients
    return refined.ingredients


async def rate_comment_confidence(
    transcript_text: str, ingredients: list[Ingredient], comment_text: str
) -> _CommentConfidence:
    """Judges dish-identity plausibility only — never quantity accuracy, see
    _SYSTEM_COMMENT_CONFIDENCE. One call per shortlisted comment (see
    comments.shortlist_recipe_like_comments), using the already-warm text
    model — no extra cold-load, unlike a vision call."""
    ingredients_json = _IngredientsOnly(ingredients=ingredients).model_dump_json()
    prompt = _build_comment_confidence_prompt(transcript_text, ingredients_json, comment_text)
    return await _chat(prompt, _CommentConfidence, _SYSTEM_COMMENT_CONFIDENCE)


async def refine_ingredients_with_comment(ingredients: list[Ingredient], comment_text: str) -> list[Ingredient]:
    """Same gap-filling shape as refine_ingredients_with_description (only
    touches ingredients still null/estimated, never invents or drops
    ingredients) but deliberately does NOT set is_estimated=false the way
    every other refine pass does — a viewer's comment is an unverified
    external claim, not something the video itself stated, so this keeps
    is_estimated=true and records provenance in `note` instead (see
    _SYSTEM_COMMENT_REFINE). Callers should only invoke this after
    rate_comment_confidence returns confidence="high"."""
    ingredients_json = _IngredientsOnly(ingredients=ingredients).model_dump_json()
    prompt = _build_comment_refine_prompt(ingredients_json, comment_text)
    want = len(ingredients)

    def is_valid(parsed: _IngredientsOnly) -> bool:
        return len(parsed.ingredients) == want

    refined, ok = await _chat_with_retry(
        prompt,
        _IngredientsOnly,
        _SYSTEM_COMMENT_REFINE,
        is_valid,
        f"Your previous response changed the ingredient count. Return exactly {want} ingredients — the "
        "same ones, in the same order — revising only their quantity/unit/note fields.",
    )
    if not ok:
        # Same alignment safety as refine_ingredients_with_ocr — don't risk
        # misapplying a value to the wrong ingredient.
        return ingredients

    # Deterministically re-assert is_estimated=true for anything this pass
    # touched, rather than trusting the model's own boolean — verified live
    # on the sparse-short-1 video: qwen2.5:7b filled real values from a
    # genuine viewer comment but flipped is_estimated=False on most changed
    # ingredients despite _SYSTEM_COMMENT_REFINE explicitly saying "you MUST
    # leave is_estimated=true". Same instruction-following gap class as the
    # "copy concrete values in" fix noted at _SYSTEM_INGREDIENT_REFINE above.
    # Two independent tells that this pass touched an ingredient, since
    # either alone missed a real case in live testing: quantity/unit
    # actually changed, OR the model added the "from a viewer's comment"
    # note marker without changing the value (observed live: an ingredient
    # an earlier, unrelated pipeline stage had already mis-marked
    # is_estimated=false with a guess that happened to match the comment —
    # the model correctly recognized the comment corroborated it and added
    # the note, but that still means the value's true provenance is this
    # comment, not something the video stated). Positional zip is safe:
    # `is_valid` already guarantees the count matches and the prompt
    # instructs the model to preserve order.
    for original, new in zip(ingredients, refined.ingredients):
        value_changed = (new.quantity, new.unit) != (original.quantity, original.unit)
        note_newly_attributed = "from a viewer's comment" in (new.note or "") and "from a viewer's comment" not in (
            original.note or ""
        )
        if value_changed or note_newly_attributed:
            new.is_estimated = True
    return refined.ingredients
