"""Deterministic cleanup of ingredient/unit data.

Every stage that fills `Ingredient.quantity`/`.unit`/`.name` is an LLM pass
(pass 1, description refinement, OCR refinement, VLM quantity estimation) —
none of them reliably produce a canonical unit string, and the model has no
concept of "this is metadata, not prose" for a field like `unit`. This
module is the single deterministic pass that cleans that up, run once at
the end of the pipeline (see orchestrator.py) rather than duplicated in
every call site, and reused verbatim by the cache-repair script
(scripts/repair_cache.py) and the eval harness (evals/metrics.py) so all
three agree on what "clean" means.

Every function here is pure and must be idempotent — `normalize_recipe`
runs again on every stale cache read (see result_cache.py), so
`normalize_recipe(normalize_recipe(r))` must equal `normalize_recipe(r)`.
"""

import re

# --- Canonical units -----------------------------------------------------
# Each canonical form maps to every spelling/abbreviation/plural variant
# observed (or plausible) in LLM output. Lookup is case-insensitive with
# periods stripped (`_unit_lookup_key`), so "Tsp", "TSp", "tsp." all resolve
# to "tsp" — this is the fix for the "TSp" vs "tsp" casing bug.
_UNIT_GROUPS: dict[str, list[str]] = {
    "tsp": ["tsp", "tsps", "t", "teaspoon", "teaspoons"],
    "tbsp": ["tbsp", "tbsps", "tbs", "tb", "tablespoon", "tablespoons"],
    "cup": ["cup", "cups", "c"],
    "g": ["g", "gr", "gram", "grams", "gm", "gms"],
    "kg": ["kg", "kgs", "kilogram", "kilograms"],
    "mg": ["mg", "mgs", "milligram", "milligrams"],
    "ml": ["ml", "mls", "milliliter", "milliliters", "millilitre", "millilitres"],
    "l": ["l", "liter", "liters", "litre", "litres"],
    "oz": ["oz", "ozs", "ounce", "ounces"],
    "fl oz": ["fl oz", "floz", "fluid ounce", "fluid ounces"],
    "lb": ["lb", "lbs", "pound", "pounds"],
    "pinch": ["pinch", "pinches"],
    "dash": ["dash", "dashes"],
    "can": ["can", "cans"],
    "stick": ["stick", "sticks"],
    "bunch": ["bunch", "bunches"],
    "sprig": ["sprig", "sprigs"],
    "head": ["head", "heads"],
    "slice": ["slice", "slices"],
    "piece": ["piece", "pieces"],
    "clove": ["clove", "cloves"],
    "handful": ["handful", "handfuls"],
    "stalk": ["stalk", "stalks"],
    "sheet": ["sheet", "sheets"],
    "packet": ["packet", "packets"],
}

CANONICAL_UNITS: dict[str, str] = {
    variant: canonical for canonical, variants in _UNIT_GROUPS.items() for variant in variants
}

# Sorted, de-duplicated list of canonical unit tokens — reused verbatim in
# the WS4 prompt glossary so the prompt and this table can't drift apart.
CANONICAL_UNIT_TOKENS: list[str] = sorted(set(CANONICAL_UNITS.values()))

_FRACTION_MAP = {
    "¼": "1/4", "½": "1/2", "¾": "3/4",
    "⅓": "1/3", "⅔": "2/3",
    "⅕": "1/5", "⅖": "2/5", "⅗": "3/5", "⅘": "4/5",
    "⅙": "1/6", "⅚": "5/6",
    "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}

# A quantity is "parseable" (safe to further manipulate) only if it matches
# this numeric grammar after fraction-folding: integer/decimal, a plain
# fraction, a mixed number, or a simple range. Anything else (a formula like
# "1.2x weight of egg whites") is left completely untouched — rule F.
_NUMERIC_RE = re.compile(
    r"^\d+(\.\d+)?$"
    r"|^\d+/\d+$"
    r"|^\d+\s+\d+/\d+$"
    r"|^\d+(\.\d+)?\s*[-–]\s*\d+(\.\d+)?$"
)

# Splits a string like "2 tbsp", "1/2 cup", or a glued "300g" into a
# leading numeric part and a trailing alpha "unit words" part. Whitespace
# between them is optional so both forms match.
_NUM_THEN_WORD_RE = re.compile(r"^\s*(?P<num>[\d./\s\-–]+?)\s*(?P<word>[a-zA-Z][a-zA-Z ]*)\s*$")

# A unit string that fails canonical lookup is treated as a stray note
# (rule C) rather than a unit if it looks like prose: a leading preposition,
# a parenthetical remark, or it's just long for a unit ("for heating up the
# pan", "(optional)").
_NOTE_LEADING_RE = re.compile(r"^(for|to|as|when|until|if|with)\b", re.IGNORECASE)
_PARENTHETICAL_RE = re.compile(r"^(?P<main>[^(]*)\((?P<paren>[^)]*)\)\s*$")

# Small allowlist of proper-noun/brand-style ingredient words that must not
# be lowercased. Deliberately tiny — anything not listed just falls back to
# lowercase, which is right for the overwhelming majority of ingredients.
_PROPER_NOUN_TERMS = {"dijon", "worcestershire", "parmesan"}

# Prep/technique descriptors that models sometimes put in `unit` instead of
# the instruction text (e.g. unit="diced", unit="chopped (optional)") — not
# units, so any `unit` string starting with one of these is treated as a
# note (rule C) rather than kept as an unrecognized-but-plausible unit.
_PREP_DESCRIPTOR_WORDS = {
    "diced", "chopped", "minced", "sliced", "grated", "crushed", "zested",
    "cubed", "quartered", "halved", "peeled", "trimmed", "julienned",
    "shredded", "crumbled", "melted", "softened", "chilled", "packed",
    "divided", "juiced",
}


def _fold_fractions(text: str) -> str:
    for uni, frac in _FRACTION_MAP.items():
        text = text.replace(uni, frac)
    return text


def _clean_str(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value.strip())
    return value or None


def _unit_lookup_key(raw: str) -> str:
    key = raw.strip().lower().replace(".", "")
    return re.sub(r"\s+", " ", key).strip()


def _lookup_unit(raw: str) -> str | None:
    return CANONICAL_UNITS.get(_unit_lookup_key(raw))


def _is_parseable_quantity(quantity: str) -> bool:
    return bool(_NUMERIC_RE.match(quantity.strip()))


def _normalize_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name.strip()).rstrip(".,;")
    tokens = name.split(" ")
    # A protected token (allowlisted proper noun, or an all-caps acronym
    # like "BBQ") means the whole name is left as-is rather than risk
    # mangling it — safer than trying to lowercase everything except that
    # one token.
    if any(t.strip(".,;").lower() in _PROPER_NOUN_TERMS or (t.isupper() and len(t) > 1) for t in tokens):
        return name
    return name.lower()


def normalize_ingredient(ing):
    """Returns a new normalized Ingredient. Import-cycle note: `Ingredient`
    is passed/returned duck-typed via `.model_copy` rather than imported at
    module scope, since app.models doesn't (and shouldn't) depend on this
    module."""
    name = _normalize_name(ing.name) if ing.name else ing.name
    quantity = _clean_str(ing.quantity)
    unit = _clean_str(ing.unit)
    note = _clean_str(getattr(ing, "note", None))

    if quantity:
        quantity = _fold_fractions(quantity)

    # Rule E: parenthetical dual measure, e.g. "300g (10.58 oz)" — the
    # conversion in parens is never load-bearing data, move it to `note`.
    if quantity:
        m = _PARENTHETICAL_RE.match(quantity)
        if m:
            main = _clean_str(m.group("main"))
            paren = _clean_str(m.group("paren"))
            quantity = main
            if paren:
                note = f"{note}; ({paren})" if note else f"({paren})"

    # Rule B: quantity is missing but the unit field actually holds
    # "<number> <unit>" (e.g. unit="2 tbsp") — split it.
    if not quantity and unit:
        m = _NUM_THEN_WORD_RE.match(unit)
        if m:
            canonical = _lookup_unit(m.group("word"))
            if canonical:
                quantity = _fold_fractions(m.group("num").strip())
                unit = canonical

    # Rule D: quantity embeds its own resolvable unit word (e.g. "1 tsp",
    # or a glued "300g") — trust it over whatever's in the `unit` field,
    # since it was emitted as one token by whichever pass produced it. This
    # covers both a genuine conflict (unit="tbsp") and the case where
    # quantity/unit already agree but are glued with no separating space
    # ("300g" + unit="g"), which Ingredient's own `_dedupe_unit_from_quantity`
    # validator can't strip (its regex requires a word boundary).
    if quantity and unit:
        m = _NUM_THEN_WORD_RE.match(quantity)
        if m:
            embedded_canonical = _lookup_unit(m.group("word"))
            if embedded_canonical:
                old_unit = unit
                quantity = _fold_fractions(m.group("num").strip())
                unit = embedded_canonical
                # The old `unit` value is being overwritten — preserve it as
                # a note if it wasn't a resolvable unit at all (a genuine
                # prep note like "chopped"/"chopped (optional)" would
                # otherwise silently vanish). A plain conflicting *unit*
                # (e.g. old unit "tbsp" overwritten by an embedded "tsp")
                # is intentionally discarded — rule D's whole point is to
                # trust the embedded pair over a stray conflicting unit,
                # not to keep both. Also skip a restated ingredient name (a
                # common model artifact, e.g. unit="onions" for an
                # ingredient named "onions").
                if _lookup_unit(old_unit) is None and old_unit.lower() != (name or "").lower():
                    note = f"{note}; {old_unit}" if note else old_unit

    # Rule A: canonicalize casing/abbreviation for a unit that's a genuine
    # unit, just spelled/cased inconsistently ("TSp" -> "tsp").
    if unit:
        canonical = _lookup_unit(unit)
        unit_words = unit.split()
        first_word_canonical = _lookup_unit(unit_words[0]) if unit_words else None
        if canonical:
            unit = canonical
        elif first_word_canonical and len(unit_words) > 1:
            # Rule C': a real unit word followed by a descriptor, e.g.
            # "cloves minced" or "cups chopped" — split rather than
            # relocating the whole thing to `note` and losing the unit.
            descriptor = unit[len(unit_words[0]):].strip()
            unit = first_word_canonical
            if descriptor:
                note = f"{note}; {descriptor}" if note else descriptor
        # Rule C: doesn't resolve to any canonical unit at all — if it
        # reads like a note rather than a unit (a leading preposition, a
        # parenthetical remark, it's just long, or it's a bare prep
        # descriptor like "diced"/"chopped" that sometimes lands in `unit`
        # instead of the instruction text), relocate it.
        elif (
            _NOTE_LEADING_RE.match(unit)
            or _PARENTHETICAL_RE.match(unit)
            or len(unit) > 12
            or unit_words[0].lower().rstrip(".,;") in _PREP_DESCRIPTOR_WORDS
        ):
            note = f"{note}; {unit}" if note else unit
            unit = None
        else:
            # Unrecognized but plausible short unit word — keep it, just
            # normalize casing.
            unit = unit.lower()

    if quantity and not _is_parseable_quantity(quantity):
        # Rule F: a formula/unparseable quantity (e.g. "1.2x weight of egg
        # whites") — never destroy information deterministically, leave it.
        pass

    # Rebuild via the constructor (not `model_copy`, which skips validation)
    # so Ingredient's own `_dedupe_unit_from_quantity` validator gets a
    # chance to run — it already handles the same-unit-embedded-in-quantity
    # case (e.g. "1.8 kg" + unit "kg") and there's no reason to duplicate
    # that logic here.
    data = ing.model_dump()
    data.update(name=name, quantity=quantity, unit=unit, note=note)
    return type(ing)(**data)


def normalize_ingredients(ingredients):
    normalized = [normalize_ingredient(ing) for ing in ingredients]
    seen: set[tuple[str, str | None, str | None]] = set()
    deduped = []
    for ing in normalized:
        key = (ing.name.lower() if ing.name else ing.name, ing.quantity, ing.unit)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ing)
    return deduped


def normalize_recipe(recipe):
    return recipe.model_copy(update={"ingredients": normalize_ingredients(recipe.ingredients)})


# --- Name-token matching --------------------------------------------------
# Shared by evals/metrics.py (predicted-vs-expected ingredient matching) and
# comments.py (WS4d — scoring whether a viewer comment mentions an
# ingredient this recipe already has), so both agree on what "the same
# ingredient name" means instead of maintaining two token-matching
# implementations that could silently drift apart.


def name_tokens(name: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", name.lower()))


def names_match(a: str, b: str) -> bool:
    if a.strip().lower() == b.strip().lower():
        return True
    a_tokens, b_tokens = name_tokens(a), name_tokens(b)
    if not a_tokens or not b_tokens:
        return False
    # Either direction counts — "onion" should match "yellow onion", and a
    # short ingredient name's tokens being a subset of a longer free-text
    # string's tokens (e.g. checking whether a comment *mentions* "garlic")
    # is exactly the same subset relationship.
    return a_tokens <= b_tokens or b_tokens <= a_tokens
