"""Standalone VLM worker, invoked as a subprocess by vlm.py.

Same rationale as _asr_worker.py: Qwen2.5-VL is loaded once per subprocess
invocation (amortizing model-load cost across every request in the batch),
and process exit guarantees its Metal memory is fully released — this runs
*after* Ollama's text pass, and Ollama's Qwen2.5 7B stays resident via
keep_alive, so isolating the VLM in its own process keeps peak memory
predictable instead of stacking two long-lived model residencies in one
Python process.

Usage: python _vlm_worker.py <model_name>
Reads a JSON array from stdin: [{"id", "image_path", "ingredient_name", "step_instruction"}, ...]
Prints a single JSON line to stdout: [{"id", "quantity", "unit", "reasoning"}, ...]
"""

import json
import re
import sys

_PROMPT_TEMPLATE = (
    "This is a still frame from a cooking video. The step being performed is: {step_instruction!r}. "
    "Based on what you can visually see in the image (pan/bowl size, amount of food, portion relative "
    "to the container), estimate a reasonable quantity for this ingredient: {ingredient_name!r}. "
    "Respond with ONLY a compact JSON object on one line. `quantity` MUST be just the number/range "
    "with NO unit words in it; `unit` holds the unit word separately, or an empty string if there isn't one: "
    '{{"quantity": "<e.g. \'2\' or \'1/2\', NEVER include the unit here>", "unit": "<e.g. \'cloves\', \'tbsp\', or \'\'>"}}'
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


def main() -> None:
    model_name = sys.argv[1]
    requests = json.loads(sys.stdin.read())

    from mlx_vlm import generate, load
    from mlx_vlm.prompt_utils import apply_chat_template

    model, processor = load(model_name)
    results = []

    for req in requests:
        prompt_text = _PROMPT_TEMPLATE.format(
            step_instruction=req["step_instruction"], ingredient_name=req["ingredient_name"]
        )
        messages = [{"role": "user", "content": prompt_text}]
        prompt = apply_chat_template(processor, model.config, messages, num_images=1)
        result = generate(model, processor, prompt, image=[req["image_path"]], verbose=False, max_tokens=80, temperature=0.1)

        quantity, unit = None, None
        try:
            text = result.text.strip()
            start, end = text.find("{"), text.rfind("}")
            parsed = json.loads(text[start : end + 1])
            quantity = (parsed.get("quantity") or "").strip() or None
            unit = (parsed.get("unit") or "").strip() or None
        except (ValueError, AttributeError, json.JSONDecodeError):
            pass  # leave as None — caller keeps the prior text-only estimate

        quantity, unit = _dedupe_unit(quantity, unit)
        results.append({"id": req["id"], "quantity": quantity, "unit": unit})

    print(json.dumps(results))


if __name__ == "__main__":
    main()
