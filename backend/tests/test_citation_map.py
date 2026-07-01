from app.models import Step, TranscriptSegment
from app.pipeline.citation_map import map_steps_to_timestamps, resolve_timestamp

SEGMENTS = [
    TranscriptSegment(text="first melt some butter in the pan", start=0.0, end=3.0),
    TranscriptSegment(text="then add the garlic and saute it", start=3.0, end=6.0),
    TranscriptSegment(text="finally serve it hot with parsley", start=6.0, end=9.0),
]


def _step(index: int, citation: str) -> Step:
    return Step(index=index, instruction="do the thing", verbatim_transcript_citation=citation)


def test_resolve_timestamp_exact_substring():
    assert resolve_timestamp("melt some butter", SEGMENTS) == 0.0
    assert resolve_timestamp("add the garlic", SEGMENTS) == 3.0


def test_resolve_timestamp_fuzzy_fallback():
    # Close but not an exact substring (minor LLM paraphrase drift)
    ts = resolve_timestamp("finally serve it hot with parsely", SEGMENTS)
    assert ts == 6.0


def test_resolve_timestamp_no_match_returns_none():
    assert resolve_timestamp("completely unrelated text about spaceships", SEGMENTS) is None


def test_resolve_timestamp_empty_citation_returns_none():
    assert resolve_timestamp("", SEGMENTS) is None
    assert resolve_timestamp("   ", SEGMENTS) is None


def test_map_steps_to_timestamps_matches_all():
    steps = [_step(1, "melt some butter"), _step(2, "add the garlic")]
    mapped, unmatched = map_steps_to_timestamps(steps, SEGMENTS, video_duration=9.0)
    assert unmatched == 0
    assert mapped[0].timestamp_seconds == 0.0
    assert mapped[1].timestamp_seconds == 3.0


def test_map_steps_to_timestamps_all_unmatched_signals_total_failure():
    # Regression test: this is the scenario a near-silent/hallucinated
    # transcript produces — every citation is bogus, and the orchestrator
    # uses unmatched == len(steps) to fail the job instead of returning a
    # fabricated recipe.
    steps = [_step(1, "something about spaceships"), _step(2, "another unrelated sentence")]
    mapped, unmatched = map_steps_to_timestamps(steps, SEGMENTS, video_duration=9.0)
    assert unmatched == len(steps)


def test_map_steps_to_timestamps_enforces_monotonicity():
    # Regression test: a short/generic citation ("serve") can fuzzy-match an
    # earlier segment than the step actually belongs to, producing a
    # backward jump in time. Timestamps must never decrease across steps.
    steps = [
        _step(1, "then add the garlic and saute it"),  # matches segment at 3.0
        _step(2, "melt some butter"),  # matches segment at 0.0 - earlier!
    ]
    mapped, _ = map_steps_to_timestamps(steps, SEGMENTS, video_duration=9.0)
    assert mapped[0].timestamp_seconds == 3.0
    assert mapped[1].timestamp_seconds == 3.0  # clamped forward, not 0.0
    assert mapped[1].timestamp_seconds >= mapped[0].timestamp_seconds
