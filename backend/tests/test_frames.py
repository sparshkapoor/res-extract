import shutil
from pathlib import Path

import pytest
from PIL import Image

from app.pipeline import frames
from app.pipeline.frames import FrameExtractionError, _average_hash, _hamming_distance, extract_distinct_frame


def _make_pattern(path: Path, kind: str) -> None:
    """Synthetic frames standing in for real video content — no ffmpeg
    needed. 'vertical'/'horizontal' are clearly different scenes;
    'vertical_noise' is a near-identical restaging of 'vertical' (same
    pattern, slightly different shading) standing in for two frames of the
    same static shot."""
    img = Image.new("RGB", (64, 64), "black")
    px = img.load()
    for x in range(64):
        for y in range(64):
            if kind == "vertical":
                px[x, y] = (255, 255, 255) if x < 32 else (0, 0, 0)
            elif kind == "horizontal":
                px[x, y] = (255, 255, 255) if y < 32 else (0, 0, 0)
            elif kind == "vertical_noise":
                px[x, y] = (250, 250, 250) if x < 32 else (5, 5, 5)
    img.save(path)


@pytest.fixture
def pattern_dir(tmp_path: Path) -> Path:
    d = tmp_path / "patterns"
    d.mkdir()
    for kind in ("vertical", "horizontal", "vertical_noise"):
        _make_pattern(d / f"{kind}.png", kind)
    return d


# --- _average_hash / _hamming_distance --------------------------------------


def test_identical_images_zero_distance(pattern_dir):
    h1 = _average_hash(pattern_dir / "vertical.png")
    h2 = _average_hash(pattern_dir / "vertical.png")
    assert _hamming_distance(h1, h2) == 0


def test_near_identical_shading_reads_as_near_duplicate(pattern_dir):
    # Same pattern, different shading — average-hash should be tolerant of
    # this (it's the "near-identical restaging" case from the plan spec).
    h_v = _average_hash(pattern_dir / "vertical.png")
    h_vn = _average_hash(pattern_dir / "vertical_noise.png")
    assert _hamming_distance(h_v, h_vn) < 6


def test_clearly_different_images_have_large_distance(pattern_dir):
    h_v = _average_hash(pattern_dir / "vertical.png")
    h_h = _average_hash(pattern_dir / "horizontal.png")
    assert _hamming_distance(h_v, h_h) >= 6


# --- extract_distinct_frame --------------------------------------------------


def _patch_extract_frame(monkeypatch, source_for_call):
    """Replaces frames.extract_frame with a fake that copies a
    pre-determined synthetic image to out_path instead of shelling out to
    ffmpeg. `source_for_call(call_index) -> Path` picks which pattern each
    successive call writes."""
    calls: list[float] = []

    async def fake_extract_frame(video_path, timestamp_seconds, out_path):
        calls.append(timestamp_seconds)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source_for_call(len(calls) - 1), out_path)
        return out_path

    monkeypatch.setattr(frames, "extract_frame", fake_extract_frame)
    return calls


@pytest.mark.asyncio
async def test_first_step_extracts_once_with_no_previous_hash(tmp_path, pattern_dir, monkeypatch):
    calls = _patch_extract_frame(monkeypatch, lambda i: pattern_dir / "vertical.png")
    out_path = tmp_path / "step_0.jpg"

    result_path, result_hash = await extract_distinct_frame(
        Path("video.mp4"), 10.0, out_path, previous_hash=None, max_timestamp=20.0
    )

    assert len(calls) == 1
    assert result_path == out_path
    assert result_hash == _average_hash(pattern_dir / "vertical.png")


@pytest.mark.asyncio
async def test_distinct_frame_accepted_without_retry(tmp_path, pattern_dir, monkeypatch):
    previous_hash = _average_hash(pattern_dir / "horizontal.png")
    calls = _patch_extract_frame(monkeypatch, lambda i: pattern_dir / "vertical.png")
    out_path = tmp_path / "step_1.jpg"

    await extract_distinct_frame(Path("video.mp4"), 10.0, out_path, previous_hash, max_timestamp=20.0)

    assert len(calls) == 1  # already distinct enough — no retry needed


@pytest.mark.asyncio
async def test_near_duplicate_retries_then_accepts_distinct_frame(tmp_path, pattern_dir, monkeypatch):
    previous_hash = _average_hash(pattern_dir / "vertical.png")

    def source_for_call(i):
        # First attempt restages the same static shot; second attempt finally
        # shows something different (e.g. the camera cut to the next beat).
        return pattern_dir / "vertical_noise.png" if i == 0 else pattern_dir / "horizontal.png"

    calls = _patch_extract_frame(monkeypatch, source_for_call)
    out_path = tmp_path / "step_2.jpg"

    _, result_hash = await extract_distinct_frame(
        Path("video.mp4"), 10.0, out_path, previous_hash, max_timestamp=20.0, min_gap=1.5
    )

    assert len(calls) == 2
    assert calls[1] == pytest.approx(11.5)  # timestamp_seconds + 1 * min_gap
    assert result_hash == _average_hash(pattern_dir / "horizontal.png")
    # The file on disk is the winning (distinct) candidate, not the first.
    assert _average_hash(out_path) == result_hash


@pytest.mark.asyncio
async def test_all_attempts_near_duplicate_never_raises_and_uses_best(tmp_path, pattern_dir, monkeypatch):
    previous_hash = _average_hash(pattern_dir / "vertical.png")
    calls = _patch_extract_frame(monkeypatch, lambda i: pattern_dir / "vertical_noise.png")
    out_path = tmp_path / "step_3.jpg"

    # Should not raise even though every candidate is a near-duplicate.
    result_path, result_hash = await extract_distinct_frame(
        Path("video.mp4"), 10.0, out_path, previous_hash, max_timestamp=100.0, max_attempts=4
    )

    assert len(calls) == 4  # exhausted every attempt
    assert result_path.exists()
    assert result_hash == _average_hash(pattern_dir / "vertical_noise.png")


@pytest.mark.asyncio
async def test_never_searches_past_max_timestamp(tmp_path, pattern_dir, monkeypatch):
    previous_hash = _average_hash(pattern_dir / "vertical.png")
    calls = _patch_extract_frame(monkeypatch, lambda i: pattern_dir / "vertical_noise.png")
    out_path = tmp_path / "step_4.jpg"

    await extract_distinct_frame(
        Path("video.mp4"), 10.0, out_path, previous_hash, max_timestamp=11.0, min_gap=1.5, max_attempts=4
    )

    assert all(ts <= 11.0 for ts in calls)
    # Capped well short of 4 attempts since the timestamp ceiling is hit fast.
    assert len(calls) < 4


@pytest.mark.asyncio
async def test_genuine_extraction_failure_still_raises(tmp_path, monkeypatch):
    async def failing_extract_frame(video_path, timestamp_seconds, out_path):
        raise FrameExtractionError("ffmpeg exploded")

    monkeypatch.setattr(frames, "extract_frame", failing_extract_frame)

    with pytest.raises(FrameExtractionError):
        await extract_distinct_frame(
            Path("video.mp4"), 10.0, tmp_path / "step_5.jpg", previous_hash=None, max_timestamp=20.0
        )


@pytest.mark.asyncio
async def test_no_leftover_temp_files(tmp_path, pattern_dir, monkeypatch):
    previous_hash = _average_hash(pattern_dir / "vertical.png")
    _patch_extract_frame(monkeypatch, lambda i: pattern_dir / "vertical_noise.png")
    out_path = tmp_path / "step_6.jpg"

    await extract_distinct_frame(Path("video.mp4"), 10.0, out_path, previous_hash, max_timestamp=100.0)

    assert list(tmp_path.glob("step_6__attempt*")) == []
    assert out_path.exists()
