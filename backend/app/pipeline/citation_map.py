import logging
from difflib import SequenceMatcher

from app.models import Step, TranscriptSegment

logger = logging.getLogger(__name__)

_FUZZY_MATCH_THRESHOLD = 0.6


def _best_fuzzy_match(citation: str, segments: list[TranscriptSegment]) -> TranscriptSegment | None:
    best_segment: TranscriptSegment | None = None
    best_ratio = 0.0
    citation_lower = citation.lower()
    for segment in segments:
        ratio = SequenceMatcher(None, citation_lower, segment.text.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_segment = segment
    return best_segment if best_ratio >= _FUZZY_MATCH_THRESHOLD else None


def _resolve_segment(citation: str, segments: list[TranscriptSegment]) -> TranscriptSegment | None:
    citation_lower = citation.strip().lower()
    if not citation_lower or not segments:
        return None

    # 1. Case-insensitive substring containment (either direction — the LLM
    #    citation might span multiple short segments or be a sub-span of one).
    for segment in segments:
        segment_lower = segment.text.lower()
        if citation_lower in segment_lower or segment_lower in citation_lower:
            return segment

    # 2. Fuzzy fallback for near-verbatim LLM drift.
    return _best_fuzzy_match(citation_lower, segments)


def resolve_timestamp(citation: str, segments: list[TranscriptSegment]) -> float | None:
    segment = _resolve_segment(citation, segments)
    return segment.start if segment is not None else None


def resolve_span(citation: str, segments: list[TranscriptSegment]) -> tuple[float, float] | None:
    """Same matching as resolve_timestamp, but returns the matched segment's
    full (start, end) span instead of just its start. Used by validate.py to
    measure how much of the transcript's timeline the steps' citations
    actually cover, not just their point-in-time order."""
    segment = _resolve_segment(citation, segments)
    return (segment.start, segment.end) if segment is not None else None


def map_steps_to_timestamps(
    steps: list[Step], segments: list[TranscriptSegment], video_duration: float
) -> tuple[list[Step], int]:
    """Resolve each step's timestamp from its citation. If a citation can't
    be matched (the LLM hallucinated a citation not present in the
    transcript), fall back to even spacing across the video duration for
    that step only — log a warning, never fail the whole job.

    Returns (steps, unmatched_count) — the caller uses unmatched_count to
    detect total extraction failure (see orchestrator's post-extraction
    sanity check: if *every* step failed to match, the LLM likely
    hallucinated the whole recipe from a garbage/near-empty transcript)."""
    n = len(steps)
    unmatched_count = 0
    for i, step in enumerate(steps):
        ts = resolve_timestamp(step.verbatim_transcript_citation, segments)
        if ts is None:
            unmatched_count += 1
            ts = (video_duration * i / max(n, 1)) if video_duration > 0 else 0.0
            logger.warning(
                "citation_map: no match for step %d citation %r — falling back to even spacing (%.1fs)",
                step.index, step.verbatim_transcript_citation, ts,
            )
        step.timestamp_seconds = ts

    # Cooking steps are inherently sequential, but short/generic citations
    # (e.g. "lemon zest") can fuzzy-match an earlier segment than intended,
    # producing a step that appears to jump backward in time. Enforce
    # non-decreasing timestamps so frame order always matches step order.
    last_ts = float("-inf")
    for step in steps:
        if step.timestamp_seconds is not None and step.timestamp_seconds < last_ts:
            step.timestamp_seconds = last_ts
        last_ts = step.timestamp_seconds if step.timestamp_seconds is not None else last_ts

    return steps, unmatched_count
