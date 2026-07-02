"""Standalone VLM worker, invoked as a subprocess by vlm.py.

Same rationale as _asr_worker.py: Qwen2.5-VL is loaded once per subprocess
invocation (amortizing model-load cost across every request in the batch),
and process exit guarantees its Metal memory is fully released — this runs
*after* Ollama's text pass, and Ollama's Qwen2.5 7B stays resident via
keep_alive, so isolating the VLM in its own process keeps peak memory
predictable instead of stacking two long-lived model residencies in one
Python process.

Usage: python _vlm_worker.py <model_name>
Reads a JSON array from stdin, one dict per request, each tagged with a
"task" field ("quantity" | "identify" | "narrate" | "hero", default "quantity"
for backward compatibility). Prints a single JSON line to stdout — one result
dict per request, same order/id-based shape regardless of task, so callers
in vlm.py parse a single result format either way.

  quantity: {"id", "image_path", "ingredient_name", "step_instruction"}
    -> {"id", "quantity", "unit"}
  identify: {"id", "image_path", "ingredient_name", "step_instruction"}
    -> {"id", "identified": [...], "confidence": "high"|"medium"|"low"}
  narrate:  {"id", "image_path"}
    -> {"id", "caption": "..."}
  hero:     {"id", "image_path"}
    -> {"id", "is_hero_shot": bool, "confidence": "high"|"medium"|"low"}
"""

import json
import re
import sys

_PROMPT_TEMPLATE_QUANTITY = (
    "This is a still frame from a cooking video. The step being performed is: {step_instruction!r}. "
    "Based on what you can visually see in the image (pan/bowl size, amount of food, portion relative "
    "to the container), estimate a reasonable quantity for this ingredient: {ingredient_name!r}. "
    "Respond with ONLY a compact JSON object on one line. `quantity` MUST be just the number/range "
    "with NO unit words in it; `unit` holds the unit word separately, or an empty string if there isn't one: "
    '{{"quantity": "<e.g. \'2\' or \'1/2\', NEVER include the unit here>", "unit": "<e.g. \'cloves\', \'tbsp\', or \'\'>"}}'
)

_PROMPT_TEMPLATE_IDENTIFY = (
    "This is a still frame from a cooking video. The step being performed is: {step_instruction!r}. "
    "The ingredient category shown is only known generically as {ingredient_name!r} (e.g. 'spices'). "
    "Based on the color, texture, and any visible packaging/labels, identify the specific spice(s) or "
    "seasoning(s) most likely shown (e.g. 'paprika', 'cumin', 'chili powder', 'black pepper'). If several "
    "are visible, list up to 3, most confident first. If you cannot identify anything specific, respond "
    "with an empty list. Respond with ONLY a compact JSON object on one line: "
    '{{"identified": ["<name>", ...], "confidence": "<high|medium|low>"}}'
)

_PROMPT_TEMPLATE_NARRATE = (
    "This is a still frame from a cooking video, sampled at a fixed interval (not aligned to any "
    "particular action). Describe what's happening in one imperative sentence, as if writing a recipe "
    "step (e.g. 'Dice the onion into small cubes.'). If no clear cooking action is visible, describe the "
    "food or ingredient shown instead (e.g. 'Sliced tomatoes on a cutting board.'). Respond with ONLY a "
    'compact JSON object on one line: {"caption": "<one imperative sentence>"}'
)

_PROMPT_TEMPLATE_HERO = (
    "This is a candidate thumbnail frame from a cooking video. Is this a clean, appetizing shot of the "
    "finished, plated dish — NOT hands or utensils in motion, NOT a close-up of a raw ingredient or "
    "empty pan, NOT a bite/reaction/mouth shot? A true hero shot shows the completed food clearly, "
    "ideally plated or served. Respond with ONLY a compact JSON object on one line: "
    '{"is_hero_shot": <true|false>, "confidence": "<high|medium|low>"}'
)


def _dedupe_unit(quantity: str | None, unit: str | None) -> tuple[str | None, str | None]:
    """The model frequently ignores the prompt's separation rule and embeds
    the unit word in `quantity` too (e.g. quantity='1 tsp', unit='tsp'),
    producing a duplicated 'quantity: "1 tsp tsp"' when the fields are
    joined for display. Strip a trailing/leading standalone occurrence of
    `unit` from `quantity` defensively, rather than trusting the model to
    follow the formatting instruction."""
    if not quantity or not unit:
        return quantity, unit
    pattern = re.compile(rf"(^|\s){re.escape(unit.strip())}(\s|$)", re.IGNORECASE)
    cleaned = pattern.sub(" ", quantity).strip()
    return (cleaned or None), unit


def _build_prompt(req: dict) -> str:
    task = req.get("task", "quantity")
    if task == "identify":
        return _PROMPT_TEMPLATE_IDENTIFY.format(
            step_instruction=req["step_instruction"], ingredient_name=req["ingredient_name"]
        )
    if task == "narrate":
        return _PROMPT_TEMPLATE_NARRATE
    if task == "hero":
        return _PROMPT_TEMPLATE_HERO
    return _PROMPT_TEMPLATE_QUANTITY.format(
        step_instruction=req["step_instruction"], ingredient_name=req["ingredient_name"]
    )


def _parse_result(req: dict, raw_text: str) -> dict:
    task = req.get("task", "quantity")
    try:
        start, end = raw_text.find("{"), raw_text.rfind("}")
        parsed = json.loads(raw_text[start : end + 1])
    except (ValueError, json.JSONDecodeError):
        parsed = {}

    if task == "identify":
        identified = parsed.get("identified") or []
        if not isinstance(identified, list):
            identified = []
        return {
            "id": req["id"],
            "identified": [str(s).strip() for s in identified if str(s).strip()],
            "confidence": parsed.get("confidence") or "low",
        }

    if task == "narrate":
        return {"id": req["id"], "caption": (parsed.get("caption") or "").strip()}

    if task == "hero":
        return {
            "id": req["id"],
            "is_hero_shot": bool(parsed.get("is_hero_shot")),
            "confidence": parsed.get("confidence") or "low",
        }

    quantity = (parsed.get("quantity") or "").strip() or None
    unit = (parsed.get("unit") or "").strip() or None
    quantity, unit = _dedupe_unit(quantity, unit)
    return {"id": req["id"], "quantity": quantity, "unit": unit}


def main() -> None:
    model_name = sys.argv[1]
    requests = json.loads(sys.stdin.read())

    from mlx_vlm import generate, load
    from mlx_vlm.prompt_utils import apply_chat_template

    model, processor = load(model_name)
    results = []

    for req in requests:
        prompt_text = _build_prompt(req)
        messages = [{"role": "user", "content": prompt_text}]
        prompt = apply_chat_template(processor, model.config, messages, num_images=1)
        result = generate(model, processor, prompt, image=[req["image_path"]], verbose=False, max_tokens=80, temperature=0.1)

        try:
            raw_text = result.text.strip()
        except AttributeError:
            raw_text = ""
        results.append(_parse_result(req, raw_text))

    print(json.dumps(results))


if __name__ == "__main__":
    main()
