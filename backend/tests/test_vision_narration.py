from app.models import TranscriptResult, TranscriptSegment
from app.pipeline import transcript
from app.pipeline.vision_narration import _sample_timestamps


def test_sample_timestamps_respects_max_frames():
    timestamps = _sample_timestamps(duration_seconds=90.0, max_frames=18, min_interval_seconds=1.5)
    assert len(timestamps) == 18
    assert timestamps[0] == 0.0
    assert all(t < 90.0 for t in timestamps)


def test_sample_timestamps_respects_min_interval_on_short_video():
    # 3s video, 1.5s floor -> at most 2 samples, never closer than 1.5s apart.
    timestamps = _sample_timestamps(duration_seconds=3.0, max_frames=18, min_interval_seconds=1.5)
    assert len(timestamps) == 2
    assert timestamps[1] - timestamps[0] >= 1.5


def test_sample_timestamps_empty_for_zero_duration():
    assert _sample_timestamps(duration_seconds=0.0, max_frames=18, min_interval_seconds=1.5) == []


def test_sample_timestamps_single_frame_for_very_short_video():
    timestamps = _sample_timestamps(duration_seconds=1.0, max_frames=18, min_interval_seconds=1.5)
    assert timestamps == [0.0]


def test_transcript_merge_sorts_real_and_synthetic_by_start_time():
    real = TranscriptResult(
        segments=[TranscriptSegment(text="add the salt", start=5.0, end=6.0)],
        source="asr",
    )
    vision = TranscriptResult(
        segments=[
            TranscriptSegment(text="Dice the onion.", start=0.0, end=3.0),
            TranscriptSegment(text="Stir the pan.", start=8.0, end=11.0),
        ],
        source="vision",
    )
    merged = transcript.merge(real, vision)
    assert merged.source == "blended"
    assert [s.start for s in merged.segments] == [0.0, 5.0, 8.0]
    assert merged.segments[1].text == "add the salt"
