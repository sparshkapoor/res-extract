"""Deterministic scoring of a predicted Recipe against a golden case's
`expected` block. Every metric here is a plain function over data — no
network, no models — so `run_eval.py --offline` can compute them in CI.
"""

import re

from app.models import Ingredient, Recipe, TranscriptSegment
from app.pipeline import citation_map
from app.pipeline.normalize import normalize_ingredient

from evals.schema import Expected, ExpectedIngredient

_FRACTION_MAP = {
    "¼": "1/4", "½": "1/2", "¾": "3/4",
    "⅓": "1/3", "⅔": "2/3",
    "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}


def _parse_quantity(raw: str | None) -> float | None:
    """Best-effort numeric value for a quantity string, for tolerance
    comparison only — returns None (never raises) for anything that isn't
    a plain number/fraction/mixed-number/range, same "don't guess at a
    formula" spirit as normalize.py's rule F."""
    if not raw:
        return None
    text = raw.strip()
    for uni, frac in _FRACTION_MAP.items():
        text = text.replace(uni, frac)

    m = re.match(r"^(\d+)\s+(\d+)/(\d+)$", text)  # mixed number "1 1/2"
    if m:
        whole, num, den = (int(g) for g in m.groups())
        return whole + num / den

    m = re.match(r"^(\d+)/(\d+)$", text)  # plain fraction "1/2"
    if m:
        num, den = (int(g) for g in m.groups())
        return num / den if den else None

    m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:[-–]|to)\s*(\d+(?:\.\d+)?)$", text)  # range
    if m:
        lo, hi = (float(g) for g in m.groups())
        return (lo + hi) / 2

    m = re.match(r"^\d+(?:\.\d+)?$", text)  # plain integer/decimal
    if m:
        return float(text)

    return None


def _name_tokens(name: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", name.lower()))


def _names_match(predicted_name: str, expected_name: str) -> bool:
    if predicted_name.strip().lower() == expected_name.strip().lower():
        return True
    p_tokens, e_tokens = _name_tokens(predicted_name), _name_tokens(expected_name)
    if not p_tokens or not e_tokens:
        return False
    # Either direction counts — "onion" (expected) should match "yellow
    # onion" (predicted), and vice versa for an over-specific expectation.
    return e_tokens <= p_tokens or p_tokens <= e_tokens


def match_ingredients(
    predicted: list[Ingredient], expected: list[ExpectedIngredient]
) -> list[tuple[Ingredient, ExpectedIngredient]]:
    """Greedy one-to-one matching by name. A recipe can legitimately use the
    same ingredient twice with different quantities (e.g. garlic in both a
    filling and a sauce — see RecipeCard.tsx's ingredient-key comment), so
    among several name-matching candidates the one whose quantity is
    closest to `exp.quantity` is preferred, not just the first found."""
    remaining = list(predicted)
    pairs = []
    for exp in expected:
        candidates = [p for p in remaining if _names_match(p.name, exp.name)]
        if not candidates:
            continue
        expected_val = _parse_quantity(exp.quantity)
        if expected_val is not None and len(candidates) > 1:
            def _distance(p: Ingredient) -> float:
                predicted_val = _parse_quantity(p.quantity)
                return abs(predicted_val - expected_val) if predicted_val is not None else float("inf")

            match = min(candidates, key=_distance)
        else:
            match = candidates[0]
        remaining.remove(match)
        pairs.append((match, exp))
    return pairs


def ingredient_f1(predicted: list[Ingredient], expected: list[ExpectedIngredient]) -> dict:
    if not expected:
        return {"precision": None, "recall": None, "f1": None}
    matches = match_ingredients(predicted, expected)
    tp = len(matches)
    precision = tp / len(predicted) if predicted else 0.0
    recall = tp / len(expected)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def unit_accuracy(predicted: list[Ingredient], expected: list[ExpectedIngredient]) -> float | None:
    matches = match_ingredients(predicted, expected)
    if not matches:
        return None
    correct = sum(1 for p, e in matches if (p.unit or None) == (e.unit or None))
    return correct / len(matches)


def quantity_accuracy(predicted: list[Ingredient], expected: list[ExpectedIngredient], tolerance: float = 0.10) -> float | None:
    matches = [(p, e) for p, e in match_ingredients(predicted, expected) if e.quantity is not None]
    if not matches:
        return None
    correct = 0
    for p, e in matches:
        expected_val = _parse_quantity(e.quantity)
        predicted_val = _parse_quantity(p.quantity)
        if expected_val is None or predicted_val is None:
            continue
        if expected_val == 0:
            correct += int(predicted_val == 0)
        elif abs(predicted_val - expected_val) / abs(expected_val) <= tolerance:
            correct += 1
    return correct / len(matches)


def citation_validity_rate(recipe: Recipe, segments: list[TranscriptSegment]) -> float:
    if not recipe.steps:
        return 0.0
    resolved = sum(
        1 for s in recipe.steps if citation_map.resolve_timestamp(s.verbatim_transcript_citation, segments) is not None
    )
    return resolved / len(recipe.steps)


def title_matches(recipe: Recipe, expected: Expected) -> bool:
    if not expected.title_contains:
        return True
    title_lower = recipe.title.lower()
    return any(term.lower() in title_lower for term in expected.title_contains)


def step_count_in_range(recipe: Recipe, expected: Expected) -> bool:
    if expected.steps_count_range is None:
        return True
    lo, hi = expected.steps_count_range
    return lo <= len(recipe.steps) <= hi


def evaluate(recipe: Recipe, expected: Expected, segments: list[TranscriptSegment]) -> dict:
    normalized_predicted = [normalize_ingredient(i) for i in recipe.ingredients]
    f1 = ingredient_f1(normalized_predicted, expected.ingredients)
    return {
        "title_matches": title_matches(recipe, expected),
        "step_count_in_range": step_count_in_range(recipe, expected),
        "ingredient_precision": f1["precision"],
        "ingredient_recall": f1["recall"],
        "ingredient_f1": f1["f1"],
        "unit_accuracy": unit_accuracy(normalized_predicted, expected.ingredients),
        "quantity_accuracy": quantity_accuracy(normalized_predicted, expected.ingredients),
        "citation_validity_rate": citation_validity_rate(recipe, segments),
    }


def aggregate(per_case_results: list[dict]) -> dict:
    """Mean of each numeric metric across cases, ignoring None (a metric
    with no applicable data for that case, e.g. no expected quantities)."""
    if not per_case_results:
        return {}
    keys = per_case_results[0].keys()
    agg: dict = {}
    for key in keys:
        values = [r[key] for r in per_case_results if r[key] is not None]
        if not values:
            agg[key] = None
        elif isinstance(values[0], bool):
            agg[key] = sum(values) / len(values)
        else:
            agg[key] = sum(values) / len(values)
    return agg
