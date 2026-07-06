"""Run the eval harness against the golden set.

--live (default): runs the real LLM chain (extract_recipe.py's passes,
  in the same order the orchestrator uses) against each golden case's
  frozen transcript/description/ocr_text, then scores the result. Needs
  Ollama running; nothing else (no yt-dlp/whisper/mlx-vlm).
--offline: skips every model call and replays a previously-saved fixture
  (see --save-fixtures) through the deterministic tail — citation_map,
  normalize, metrics — so it can run in CI/pytest with no models at all.
--save-fixtures: (only meaningful with --live) freezes the raw post-LLM,
  pre-citation-map recipe for each case to evals/fixtures/<id>.json, for
  later --offline replay.
--case <id>: limit to one golden case.

Usage:
    PYTHONPATH=. .venv/bin/python evals/run_eval.py --live
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
from app.pipeline import citation_map, extract_recipe, transcript
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
    """Mirrors orchestrator.py's LLM-only stages, in order: pass 1 ->
    description refine -> OCR refine -> proofread. Deliberately stops
    before citation mapping / normalize so the fixture captures exactly
    the recipe state a real run would hand to citation_map."""
    recipe = await extract_recipe.call_llm(case.transcript.full_text, case.url, case.platform)
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


async def evaluate_live(case: GoldenCase, save_fixture: bool) -> dict:
    raw_recipe = await _run_llm_chain(case)
    if save_fixture:
        FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        (FIXTURES_DIR / f"{case.id}.json").write_text(raw_recipe.model_dump_json(indent=2))
    recipe = _finish(raw_recipe, case)
    return metrics.evaluate(recipe, case.expected, case.transcript.segments)


def evaluate_offline(case: GoldenCase) -> dict | None:
    fixture_path = FIXTURES_DIR / f"{case.id}.json"
    if not fixture_path.exists():
        print(f"  [skip] no fixture for {case.id!r} — run --live --save-fixtures first")
        return None
    raw_recipe = Recipe.model_validate_json(fixture_path.read_text())
    recipe = _finish(raw_recipe, case)
    return metrics.evaluate(recipe, case.expected, case.transcript.segments)


def _print_case(case_id: str, result: dict) -> None:
    parts = [f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in result.items()]
    print(f"  {case_id}: {', '.join(parts)}")


async def main(live: bool, case_filter: str | None, save_fixtures: bool) -> None:
    cases = load_golden_cases(case_filter)
    if not cases:
        print("No matching golden cases found in evals/golden/")
        sys.exit(1)

    print(f"[run_eval] mode={'live' if live else 'offline'}  cases={len(cases)}")
    results: dict[str, dict] = {}
    for case in cases:
        if live:
            result = await evaluate_live(case, save_fixtures)
        else:
            result = evaluate_offline(case)
        if result is None:
            continue
        results[case.id] = result
        _print_case(case.id, result)

    agg = metrics.aggregate(list(results.values()))
    print("\n[run_eval] aggregate:")
    _print_case("(mean)", agg)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(json.dumps({"mode": "live" if live else "offline", "cases": results, "aggregate": agg}, indent=2))
    print(f"\n[run_eval] report written to {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="run the real LLM chain against Ollama (default)")
    mode.add_argument("--offline", action="store_true", help="replay saved fixtures, no models")
    parser.add_argument("--case", default=None, help="limit to one golden case id")
    parser.add_argument("--save-fixtures", action="store_true", help="freeze live LLM output for offline replay")
    args = parser.parse_args()

    asyncio.run(main(live=not args.offline, case_filter=args.case, save_fixtures=args.save_fixtures))
