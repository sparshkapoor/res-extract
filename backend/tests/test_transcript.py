from app.models import TranscriptSegment
from app.pipeline.transcript import budget_segments, compact_segments, estimate_tokens


def _seg(text: str, start: float, end: float) -> TranscriptSegment:
    return TranscriptSegment(text=text, start=start, end=end)


# --- compact_segments -----------------------------------------------------


def test_drops_filler_segments():
    segments = [_seg("[Music]", 0.0, 1.0), _seg("Melt the butter in a pan.", 1.0, 3.0)]
    result = compact_segments(segments)
    assert [s.text for s in result] == ["Melt the butter in a pan."]


def test_drops_note_symbol_filler():
    segments = [_seg("♪", 0.0, 1.0), _seg("Add the flour.", 1.0, 2.0)]
    result = compact_segments(segments)
    assert [s.text for s in result] == ["Add the flour."]


def test_drops_consecutive_duplicate_segments():
    # Whisper repetition-looping on near-silent audio.
    segments = [
        _seg("thank you", 0.0, 1.0),
        _seg("thank you", 1.0, 2.0),
        _seg("thank you", 2.0, 3.0),
        _seg("Now add the salt.", 3.0, 4.0),
    ]
    result = compact_segments(segments)
    assert [s.text for s in result] == ["thank you", "Now add the salt."]


def test_merges_consecutive_micro_segments_preserving_span():
    segments = [
        _seg("Okay", 0.0, 0.5),
        _seg("so", 0.5, 0.8),
        _seg("next up we melt the butter in a pan.", 0.8, 3.0),
    ]
    result = compact_segments(segments)
    assert len(result) == 2
    assert result[0].text == "Okay so"
    assert result[0].start == 0.0
    assert result[0].end == 0.8
    assert result[1].text == "next up we melt the butter in a pan."


def test_compact_segments_is_idempotent():
    segments = [
        _seg("[Applause]", 0.0, 1.0),
        _seg("um", 1.0, 1.2),
        _seg("So first melt the butter.", 1.2, 3.0),
        _seg("So first melt the butter.", 3.0, 3.1),
    ]
    once = compact_segments(segments)
    twice = compact_segments(once)
    assert [s.text for s in once] == [s.text for s in twice]


def test_compact_segments_keeps_citable_text_verbatim():
    # A citation the LLM copies verbatim from a surviving segment must stay
    # a valid substring after compaction — compaction must never rewrite
    # text inside a segment that survives, only drop/merge whole ones.
    citation = "melt a stick of butter in a pan over medium heat"
    segments = [_seg("[Music]", 0.0, 1.0), _seg(f"Okay so first {citation}.", 1.0, 4.0)]
    result = compact_segments(segments)
    assert citation in " ".join(s.text for s in result)


# --- estimate_tokens / budget_segments -------------------------------------


def test_estimate_tokens_scales_with_length():
    assert estimate_tokens("a" * 35) == 10


def test_budget_segments_no_truncation_when_under_budget():
    segments = [_seg("short transcript.", 0.0, 1.0)]
    result, truncated = budget_segments(segments, max_tokens=1000)
    assert result == segments
    assert truncated is False


def test_budget_segments_drops_from_the_tail_when_over_budget():
    segments = [
        _seg("first segment with some words in it", 0.0, 1.0),
        _seg("second segment with some words in it", 1.0, 2.0),
        _seg("third segment with some words in it", 2.0, 3.0),
    ]
    # Small enough budget that only the first segment survives.
    result, truncated = budget_segments(segments, max_tokens=estimate_tokens(segments[0].text))
    assert truncated is True
    assert result == [segments[0]]


def test_budget_segments_never_drops_to_empty():
    segments = [_seg("a single very long segment " * 20, 0.0, 1.0)]
    result, truncated = budget_segments(segments, max_tokens=1)
    assert truncated is True
    assert result == [segments[0]]
