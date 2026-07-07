"""Deterministic recipe-level quality checks that run after citation mapping
but before frame extraction/OCR/VLM, so a corrective retry (see
orchestrator.py) never wastes that work.

Complements citation_map.py's hallucination guard, which only checks that a
step's citation resolves to *some* timestamp — a single, terse, but
correctly-cited step (e.g. "step 1: mix all the ingredients" on a 5-action
recipe) passes that guard fine. This module catches step *quality*: is
there a plausible number of steps for this video's length/narration density,
are any steps suspiciously terse or a known collapse phrase, do the step
citations actually span the transcript's timeline, and is every extracted
ingredient referenced by at least one step.
"""

import math
import re

from pydantic import BaseModel

from app.models import Recipe, Step, TranscriptSegment
from app.pipeline import citation_map

# --- Step-count floor -------------------------------------------------------
# A video can't reasonably need more than ~8 steps just because it runs long
# (that's over-segmentation, not under-segmentation), and even a very short
# clip narrating a real recipe needs at least 3 to avoid a single "do
# everything" step passing unflagged.
_STEP_FLOOR_MIN = 3
_STEP_FLOOR_MAX = 8
_SECONDS_PER_STEP = 25
_SEGMENTS_PER_STEP = 4

# --- Terse-step detection ----------------------------------------------------
_TERSE_MAX_WORDS = 6
_TERSE_MIN_INGREDIENTS = 4
_COLLAPSE_PATTERNS = [
    re.compile(r"\b(mix|combine|add)\b[^.]*\ball\b[^.]*\bingredients\b", re.IGNORECASE),
    re.compile(r"^\s*prepare\s+the\b", re.IGNORECASE),
]

# --- Verbosity ceiling -------------------------------------------------------
_VERBOSE_MAX_WORDS = 45


def expected_min_steps(duration_seconds: float, segment_count: int) -> int:
    """Duration- and transcript-aware step-count floor. A 60s reel with
    dense narration should not yield 1-2 steps just because it's short."""
    by_duration = math.ceil(duration_seconds / _SECONDS_PER_STEP) if duration_seconds > 0 else _STEP_FLOOR_MIN
    by_duration = max(_STEP_FLOOR_MIN, min(by_duration, _STEP_FLOOR_MAX))
    by_transcript = math.ceil(segment_count / _SEGMENTS_PER_STEP) if segment_count > 0 else 0
    return max(by_duration, by_transcript)


def _is_terse(instruction: str, ingredient_count: int) -> bool:
    # A genuinely simple recipe (few ingredients) can legitimately have a
    # short step — only flag terseness when the recipe is complex enough
    # that a short/collapsed step is suspicious.
    if ingredient_count < _TERSE_MIN_INGREDIENTS:
        return False
    if len(instruction.split()) < _TERSE_MAX_WORDS:
        return True
    return any(p.search(instruction) for p in _COLLAPSE_PATTERNS)


def _is_verbose(instruction: str) -> bool:
    return len(instruction.split()) > _VERBOSE_MAX_WORDS


def _transcript_coverage(steps: list[Step], segments: list[TranscriptSegment]) -> float:
    """Fraction of the transcript's timeline spanned by the union of each
    step's matched citation segment. Low coverage means the model skipped
    over narrated content, not that narration was sparse to begin with."""
    if not segments:
        return 1.0  # nothing to cover (e.g. a vision-only synthesized transcript)
    timeline_start = min(s.start for s in segments)
    timeline_end = max(s.end for s in segments)
    total = timeline_end - timeline_start
    if total <= 0:
        return 1.0

    windows = [
        span
        for step in steps
        if (span := citation_map.resolve_span(step.verbatim_transcript_citation, segments)) is not None
    ]
    if not windows:
        return 0.0

    windows.sort()
    covered = 0.0
    cur_start, cur_end = windows[0]
    for start, end in windows[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            covered += cur_end - cur_start
            cur_start, cur_end = start, end
    covered += cur_end - cur_start
    return min(1.0, covered / total)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _unreferenced_ingredients(recipe: Recipe) -> list[str]:
    step_tokens: set[str] = set()
    for step in recipe.steps:
        step_tokens |= _tokens(step.instruction)
    return [
        ing.name
        for ing in recipe.ingredients
        if (name_tokens := _tokens(ing.name)) and not (name_tokens & step_tokens)
    ]


class ValidationResult(BaseModel):
    expected_min_steps: int
    step_count_ok: bool
    terse_step_indexes: list[int]
    verbose_step_indexes: list[int]
    transcript_coverage: float
    unreferenced_ingredients: list[str]

    @property
    def needs_retry(self) -> bool:
        """Only step-count/terseness issues are worth a full pass-1 retry —
        verbosity and unreferenced ingredients are logged/surfaced (and, for
        verbosity, handled by a targeted split in the proofread pass) but
        never block on their own."""
        return not self.step_count_ok or bool(self.terse_step_indexes)


def validate_recipe(recipe: Recipe, segments: list[TranscriptSegment], duration_seconds: float) -> ValidationResult:
    min_steps = expected_min_steps(duration_seconds, len(segments))
    ingredient_count = len(recipe.ingredients)
    return ValidationResult(
        expected_min_steps=min_steps,
        step_count_ok=len(recipe.steps) >= min_steps,
        terse_step_indexes=[s.index for s in recipe.steps if _is_terse(s.instruction, ingredient_count)],
        verbose_step_indexes=[s.index for s in recipe.steps if _is_verbose(s.instruction)],
        transcript_coverage=_transcript_coverage(recipe.steps, segments),
        unreferenced_ingredients=_unreferenced_ingredients(recipe),
    )


def build_corrective_note(recipe: Recipe, result: ValidationResult, duration_seconds: float) -> str:
    """User-message addendum for the one bounded pass-1 retry (see
    orchestrator.py) — built from this specific attempt's findings rather
    than a generic nudge, so the retry has concrete numbers to react to."""
    lines = [
        f"Your previous attempt produced {len(recipe.steps)} steps for a {duration_seconds:.0f}s video "
        f"whose transcript describes multiple distinct actions (at least {result.expected_min_steps} "
        "steps expected here). Break compound actions into separate steps — each step = one action with "
        "the specific ingredients, quantities, technique, and doneness cues stated or shown. Do not "
        "invent actions not in the transcript."
    ]
    if result.terse_step_indexes:
        lines.append(
            f"Steps at index {result.terse_step_indexes} were too terse or collapsed multiple actions "
            "into one (e.g. \"mix all the ingredients\") — split each into its own step naming the "
            "specific ingredients/technique involved."
        )
    return " ".join(lines)
