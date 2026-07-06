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

`--live` runs `extract_recipe.call_llm` -> description refine -> OCR refine
-> proofread, in the same order `orchestrator.py` uses, then
`citation_map.map_steps_to_timestamps` + `normalize.normalize_recipe`, then
scores the result with `metrics.py`. `--save-fixtures` freezes the raw
post-LLM/pre-citation-map recipe to `fixtures/<id>.json` so `--offline` can
replay just the deterministic tail (citation_map, normalize, metrics) with
no models at all — safe for CI/pytest.

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

Not yet added (arrives with WS4a): step-coverage %, terse-step rate,
instruction-length stats. `Expected.min_transcript_coverage` and
`max_terse_steps` already exist as optional fields for when that lands.

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
