# Eval harness

Measures whether a change to the LLM chain (prompts, transcript
compaction, model swap) actually helps, instead of guessing. Built
*before* any prompt changes so those changes have a baseline to beat.

## How it works

A **golden case** (`golden/<id>.json`, `schema.GoldenCase`) freezes exactly
what the LLM chain sees before any model call: the transcript, the video's
own written description, and (optionally) OCR text — plus a hand-corrected
`expected` block. Freezing the inputs means a `--live` run only calls
Ollama; it never touches yt-dlp, whisper, or mlx-vlm, so it's fast and
repeatable.

```
PYTHONPATH=. .venv/bin/python evals/run_eval.py --live
PYTHONPATH=. .venv/bin/python evals/run_eval.py --live --case rye-pitas --save-fixtures
PYTHONPATH=. .venv/bin/python evals/run_eval.py --offline   # no models, replays saved fixtures
```

`--live` runs `extract_recipe.call_llm` -> citation mapping ->
`validate.validate_recipe` (one bounded corrective retry if it flags
too-few/terse steps, keeping whichever attempt scores higher
`transcript_coverage`) -> description refine -> OCR refine -> proofread, in
the same order `orchestrator.py` uses, then a final
`citation_map.map_steps_to_timestamps` + `normalize.normalize_recipe`, then
scores the result with `metrics.py`. `--save-fixtures` freezes the raw
post-LLM/pre-citation-map recipe to `fixtures/<id>.json` so `--offline` can
replay just the deterministic tail (citation_map, normalize, metrics) with
no models at all — safe for CI/pytest.

**`--trials N`** repeats each live case N times and reports the mean plus
the min-max range per metric. Use this for any real accept/reject decision
— a single live run at `llm_temperature=0.1` has been observed to swing
`unit_accuracy` 0.58-0.92 and `quantity_accuracy` 0.58-0.96 on the exact
same code, so one sample cannot reliably distinguish a real regression
from noise.

## Metrics (`metrics.py`)

All computed after running each ingredient through
`normalize.normalize_ingredient`, so the harness measures the pipeline's
real output quality, not raw LLM noise the normalizer already fixes:

- **ingredient precision/recall/F1** — name-matched (exact or token-subset,
  so "onion" matches "yellow onion"), with a quantity-aware tie-break for
  legitimate same-name duplicates (e.g. garlic used in both a filling and a
  sauce with different quantities).
- **unit_accuracy** / **quantity_accuracy** (±10% tolerance) — among
  name-matched pairs only.
- **citation_validity_rate** — reuses `citation_map.resolve_timestamp`
  directly, so this metric can never disagree with the real hallucination
  guard.
- **step_count_in_range**, **title_matches** — coarse sanity checks.
- **transcript_coverage**, **terse_step_rate**, **mean/max_instruction_words**,
  **step_count_floor_pass** (WS4a) — reuse `validate.py` directly rather
  than reimplementing step-granularity scoring, so this harness and the
  live pipeline's own corrective-retry gate can never disagree on what
  "terse"/"low coverage" means. `Expected.min_transcript_coverage` /
  `max_terse_steps` gate `min_coverage_ok`/`terse_steps_ok` when a golden
  case sets them (`None` means not checked).

## capture.py — building a new golden case

```
PYTHONPATH=. .venv/bin/python evals/capture.py "<url>" --id <slug>
```

Runs the real download + transcript stages (yt-dlp, native captions or
mlx-whisper) against a live URL, then prefills `expected` from that URL's
existing `result_cache` entry if one exists — a starting point, not a
finished golden case. **Always hand-review and correct `expected` before
trusting it** — see `golden/rye-pitas.json` for an example where the
video's own written description (far more precise than the spoken
transcript) was used to build a complete, accurate expected-ingredients
list, including ingredients the current pipeline doesn't yet extract
correctly (that's the point — it's supposed to catch real gaps).

## Current golden cases

- **`rye-pitas`** — a long, two-component recipe (filling + sauce) with a
  precise written description. Exercises ingredient F1/unit/quantity
  accuracy broadly; not the short-video collapse failure class.
- **`sparse-short-1`** (a 17s "Simple Sauces" Short, captured from a
  user-provided URL) — the reported failure class itself: dense-looking
  auto-caption segments (9 overlapping ~4s windows) but only *one* of them
  actually names ingredients/action; no written description at all.
  `qwen2.5:7b`'s first pass-1 attempt reliably collapses this into a
  single (well-worded, not "terse" by the word-count heuristic) step citing
  that one segment; `validate.py`'s step-count floor still flags it
  (`step_count_ok=False`, 1 < 3) and the bounded retry splits it into ~5
  steps, each naming one action, which wins on `transcript_coverage` and
  is what orchestrator.py adopts. `expected.steps_count_range=[3, 6]` is
  the regression check for this: if it ever collapses back to 1-2 steps,
  this case fails.
  - `min_transcript_coverage` and `max_terse_steps` are deliberately left
    `null` for this case: only ~1 of the video's 9 nominal segments is
    actionable content (the rest is intro/outro chatter), so
    `transcript_coverage` has a low structural ceiling (~0.23) regardless
    of extraction quality — not a useful gate here. Similarly, the
    5-step retry still has one legitimately short-but-correct step
    ("Stir in rice vinegar.") that the word-count-based terse heuristic
    flags as a false positive — `_is_terse`'s <6-word rule is deliberately
    coarse (per the plan) and accepts this kind of false positive as the
    cost of cheaply catching real collapses, so gating `max_terse_steps=0`
    on this case would fail structurally, not meaningfully.
  - `expected.ingredients` includes `"gochujang"`, but the auto-generated
    captions consistently mis-transcribe it as "go jang"/"gou jang" (never
    correctly), and there's no written description to cross-reference —
    so this ingredient will show as a permanent recall miss in this case's
    F1 score. That's a real, separate defect (ASR garbling an ingredient
    name with no correction path today) worth fixing later, not a WS4a
    bug — left as an honest gap rather than papered over by expecting the
    garbled transcription.

## Why this instead of fine-tuning

Fine-tuning a 7B model on cooking-transcript-to-recipe pairs without an
eval set is flying blind — no way to tell if a LoRA actually helped or
just overfit to a handful of examples. This harness is deliberately the
*first* investment: input engineering (prompts, transcript compaction) and
deterministic post-processing (`normalize.py`) recover most of the
available quality for free, and every golden case hand-corrected here
doubles as future SFT data.

**Deferred LoRA path:** once ~50+ golden cases exist (each is a real,
hand-verified `transcript -> recipe` pair), an `mlx-lm` LoRA adapter for
`qwen2.5:7b` (or whatever text model WS4b lands on) trained on
`(compacted transcript -> recipe JSON)` becomes worth the effort. No
training code exists yet — this harness is what makes that decision
measurable instead of a guess, and its golden set is the training data
whenever that day comes.
