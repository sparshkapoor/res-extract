"""Run the eval harness against the golden set.

--live (default): runs the real LLM chain (extract_recipe.py's passes,
  in the same order the orchestrator uses) against each golden case's
  frozen transcript/description/ocr_text, then scores the result. Needs
  Ollama running; nothing else (no yt-dlp/whisper/mlx-vlm).
--offline: skips every model call and replays a previously-saved fixture
  (see --save-fixtures) through the deterministic tail — citation_map,
  normalize, metrics — so it can run in CI/pytest with no models at all.
--trials N: (only meaningful with --live) repeats each case N times and
  reports the mean, plus the min-max range per metric when N > 1. A single
  live run is noisy — even at llm_temperature=0.1, back-to-back runs on the
  same golden case have been observed to swing unit_accuracy 0.58-0.92 and
  quantity_accuracy 0.58-0.96 — so a single sample is not a reliable signal
  for accepting or rejecting a prompt change. Default 1 for a quick smoke
  check; use 5+ before deciding a change is a real regression or win.
--save-fixtures: (only meaningful with --live) freezes the raw post-LLM,
  pre-citation-map recipe for each case to evals/fixtures/<id>.json, for
  later --offline replay. With --trials > 1, freezes whichever trial ran
  last — trials only affect metric averaging, not which recipe is frozen.
--case <id>: limit to one golden case.

Usage:
    PYTHONPATH=. .venv/bin/python evals/run_eval.py --live
    PYTHONPATH=. .venv/bin/python evals/run_eval.py --live --trials 5
    PYTHONPATH=. .venv/bin/python evals/run_eval.py --offline
    PYTHONPATH=. .venv/bin/python evals/run_eval.py --live --case rye-pitas --save-fixtures
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.models import Recipe, TranscriptResult
from app.pipeline import citation_map, extract_recipe, transcript, validate
from app.pipeline.normalize import normalize_recipe

from evals import metrics
from evals.schema import GoldenCase

EVALS_DIR = Path(__file__).resolve().parent
GOLDEN_DIR = EVALS_DIR / "golden"
FIXTURES_DIR = EVALS_DIR / "fixtures"
REPORTS_DIR = EVALS_DIR / "reports"


def load_golden_cases(case_filter: str | None) -> list[GoldenCase]:
    paths = sorted(GOLDEN_DIR.glob("*.json"))
    cases = [GoldenCase.model_validate_json(p.read_text()) for p in paths]
    if case_filter:
        cases = [c for c in cases if c.id == case_filter]
    for case in cases:
        # Same compaction the real orchestrator applies before pass 1 — must
        # match here too, since _run_llm_chain and _finish (citation_map)
        # both key off case.transcript and would otherwise diverge from what
        # a live run actually sees. Token budgeting is deliberately skipped:
        # it's a rare-case safety valve for pathologically long transcripts,
        # and golden cases are frozen short fixtures that will never hit it.
        case.transcript = TranscriptResult(
            segments=transcript.compact_segments(case.transcript.segments),
            source=case.transcript.source,
        )
    return cases


async def _run_llm_chain(case: GoldenCase) -> Recipe:
    """Mirrors orchestrator.py's stages, in order: pass 1 -> citation mapping
    -> step-granularity validation with a bounded corrective retry (WS4a) ->
    description refine -> OCR refine -> proofread. The retry decision needs
    citations already mapped, so this does an early citation_map pass of its
    own — harmless since _finish()'s later pass is deterministic given the
    same steps/segments and simply reproduces the same timestamps. Without
    mirroring the retry here, eval numbers would understate what production
    actually delivers to users (who get the retry's second chance)."""
    recipe = await extract_recipe.call_llm(case.transcript.full_text, case.url, case.platform)
    recipe.steps, _unmatched = citation_map.map_steps_to_timestamps(
        recipe.steps, case.transcript.segments, case.duration_seconds
    )
    validation = validate.validate_recipe(recipe, case.transcript.segments, case.duration_seconds)
    if validation.needs_retry:
        corrective_note = validate.build_corrective_note(recipe, validation, case.duration_seconds)
        retry_recipe = await extract_recipe.call_llm(
            case.transcript.full_text, case.url, case.platform, corrective_note=corrective_note
        )
        if retry_recipe.steps:
            retry_recipe.steps, _retry_unmatched = citation_map.map_steps_to_timestamps(
                retry_recipe.steps, case.transcript.segments, case.duration_seconds
            )
            retry_validation = validate.validate_recipe(
                retry_recipe, case.transcript.segments, case.duration_seconds
            )
            if retry_validation.transcript_coverage > validation.transcript_coverage:
                recipe = retry_recipe

    if case.description:
        recipe.ingredients = await extract_recipe.refine_ingredients_with_description(
            recipe.ingredients, case.description
        )
    if case.ocr_text:
        recipe.ingredients = await extract_recipe.refine_ingredients_with_ocr(recipe.ingredients, case.ocr_text)
    recipe.steps = await extract_recipe.proofread_steps(recipe.steps)
    return recipe


def _finish(recipe: Recipe, case: GoldenCase) -> Recipe:
    recipe.steps, _unmatched = citation_map.map_steps_to_timestamps(
        recipe.steps, case.transcript.segments, case.duration_seconds
    )
    return normalize_recipe(recipe)


async def evaluate_live(case: GoldenCase, save_fixture: bool, trials: int) -> dict:
    """Runs the case `trials` times and returns {"trials": [per-trial dict,
    ...], "mean": averaged dict} — see module docstring for why a single
    live run is too noisy to gate a prompt change on."""
    trial_results = []
    raw_recipe = None
    for _ in range(trials):
        raw_recipe = await _run_llm_chain(case)
        recipe = _finish(raw_recipe, case)
        trial_results.append(
            metrics.evaluate(recipe, case.expected, case.transcript.segments, case.duration_seconds)
        )
    if save_fixture and raw_recipe is not None:
        FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        (FIXTURES_DIR / f"{case.id}.json").write_text(raw_recipe.model_dump_json(indent=2))
    return {"trials": trial_results, "mean": metrics.aggregate(trial_results)}


def evaluate_offline(case: GoldenCase) -> dict | None:
    fixture_path = FIXTURES_DIR / f"{case.id}.json"
    if not fixture_path.exists():
        print(f"  [skip] no fixture for {case.id!r} — run --live --save-fixtures first")
        return None
    raw_recipe = Recipe.model_validate_json(fixture_path.read_text())
    recipe = _finish(raw_recipe, case)
    result = metrics.evaluate(recipe, case.expected, case.transcript.segments, case.duration_seconds)
    # A frozen-fixture replay is fully deterministic — no sampling variance
    # to average over, so it's always exactly one "trial".
    return {"trials": [result], "mean": result}


def _format_metrics(result: dict) -> str:
    return ", ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in result.items())


def _trial_range(trials: list[dict], key: str) -> str | None:
    values = [t[key] for t in trials if isinstance(t.get(key), float)]
    if len(values) < 2:
        return None
    return f"{min(values):.2f}-{max(values):.2f}"


def _print_case(case_id: str, case_result: dict) -> None:
    mean = case_result["mean"]
    trials = case_result["trials"]
    print(f"  {case_id}: {_format_metrics(mean)}")
    if len(trials) > 1:
        ranges = [f"{k}={r}" for k in mean if isinstance(mean[k], float) and (r := _trial_range(trials, k))]
        if ranges:
            print(f"    range across {len(trials)} trials: {', '.join(ranges)}")


async def main(live: bool, case_filter: str | None, save_fixtures: bool, trials: int) -> None:
    cases = load_golden_cases(case_filter)
    if not cases:
        print("No matching golden cases found in evals/golden/")
        sys.exit(1)

    trial_note = f"  trials={trials}" if live else ""
    print(f"[run_eval] mode={'live' if live else 'offline'}  cases={len(cases)}{trial_note}")
    results: dict[str, dict] = {}
    for case in cases:
        if live:
            result = await evaluate_live(case, save_fixtures, trials)
        else:
            result = evaluate_offline(case)
        if result is None:
            continue
        results[case.id] = result
        _print_case(case.id, result)

    agg = metrics.aggregate([r["mean"] for r in results.values()])
    print("\n[run_eval] aggregate:")
    print(f"  (mean): {_format_metrics(agg)}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(
        json.dumps(
            {"mode": "live" if live else "offline", "trials": trials, "cases": results, "aggregate": agg},
            indent=2,
        )
    )
    print(f"\n[run_eval] report written to {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="run the real LLM chain against Ollama (default)")
    mode.add_argument("--offline", action="store_true", help="replay saved fixtures, no models")
    parser.add_argument("--case", default=None, help="limit to one golden case id")
    parser.add_argument("--save-fixtures", action="store_true", help="freeze live LLM output for offline replay")
    parser.add_argument(
        "--trials", type=int, default=1,
        help="repeat each live case N times and average (reduces sampling noise); ignored in --offline mode",
    )
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be >= 1")

    asyncio.run(main(live=not args.offline, case_filter=args.case, save_fixtures=args.save_fixtures, trials=args.trials))
