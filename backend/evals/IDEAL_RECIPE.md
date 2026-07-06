# Ideal recipe rubric

Concrete checklist, not prose — derived from the original data-quality audit
(9 recipes in `backend/storage/db.sqlite3`) and from `golden/rye-pitas.json`,
the reference recipe the user identified as structurally closest to what
every extraction should look like once its defects are fixed.

Use this to manually judge a real extraction (e.g. after
`smoke_test.py <url> --force`), separately from the aggregate metrics in
`metrics.py` (which score breadth across many recipes, not "does this one
specific recipe look right").

## Checklist

- [ ] **Units** — every `unit` is either `null` or one of `normalize.CANONICAL_UNIT_TOKENS`,
      lowercase, no free text (`normalize.py` rules A/C/C').
- [ ] **No quantity/unit swap** — no ingredient has its quantity sitting in
      `unit` (rule B) or a unit word left in `quantity` (rule D).
- [ ] **Notes preserved, not lost** — prep asides ("chopped", "(optional)",
      a unit conversion) show up in `note`, never silently dropped and never
      left polluting `unit`.
- [ ] **Casing** — ingredient names are lowercase except genuine proper
      nouns/acronyms (rule G).
- [ ] **No accidental dedup / no missed dedup** — the same ingredient used
      twice with different quantities (e.g. garlic in a filling AND a sauce)
      appears as two entries; true exact duplicates are collapsed to one.
- [ ] **Step granularity** — no single step collapses an entire multi-action
      component into "mix all the ingredients" when the video shows several
      distinct actions (tracked by WS4a's step-validation, not yet built).
- [ ] **Step photos are distinct** — no two steps show the same/near-identical
      frame (tracked by WS4c, not yet built).
- [ ] **Hero image present and renders immediately** — `hero_image_path` is
      set, and the frontend shows it crisp at scroll position 0, not blurred
      (tracked by WS6a, not yet built).
- [ ] **Title is accurate** — reflects what the video/description actually
      calls the dish. Known trap: ASR can mishear a proper noun (this
      recipe's own transcript literally mishears "Arayes" as "a rye", which
      is how the cached recipe ended up titled "Rye Pitas" — a real dish
      name doesn't exist called that). Prefer the written description over
      a transcript mishearing when they conflict.
- [ ] **Metadata only when stated** — `cook_time_minutes`/`servings`/`calories`/
      `oven_temp_f` are populated only when the video states or clearly
      implies them; null otherwise, never guessed.

## Known limitation

Rule C' (unit-word-plus-descriptor splitting, e.g. "cloves minced" ->
unit="clove", note="minced") was added *after* the initial repair pass had
already collapsed some rows' unit text entirely into `note`. Re-running
normalize on that already-collapsed state can't recover the unit, since the
original raw model output is gone. Where this happened live in production
data, `note` may contain a slightly redundant word (e.g. "cloves minced"
instead of just "minced") — cosmetic only, not misleading. A full
`smoke_test.py <url> --force` re-extraction is the only way to get a fully
pristine result for an already-cached recipe.

## Status against golden/rye-pitas.json

Not yet run — WS4a (step validation) and WS4c (step-photo distinctness)
don't exist yet, and the plan calls for checking this rubric after both
land, not before. See MEMORY/plan file for the current workstream order.
