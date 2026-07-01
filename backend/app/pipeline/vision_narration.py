import logging
from pathlib import Path

from app.config import Settings
from app.models import TranscriptResult, TranscriptSegment
from app.pipeline import frames, ocr, vlm

logger = logging.getLogger(__name__)


def _sample_timestamps(duration_seconds: float, max_frames: int, min_interval_seconds: float) -> list[float]:
    """Evenly-spaced sample points across the video, capped at `max_frames`
    and never closer together than `min_interval_seconds`."""
    if duration_seconds <= 0 or max_frames <= 0:
        return []
    count = min(max_frames, max(1, int(duration_seconds / min_interval_seconds)))
    interval = duration_seconds / count
    return [round(i * interval, 3) for i in range(count)]


async def build_vision_transcript(
    video_path: Path, duration_seconds: float, tmp_frames_dir: Path, settings: Settings
) -> TranscriptResult:
    """Synthesizes a timestamped TranscriptResult from sampled video frames,
    for videos with insufficient spoken narration. Each sampled frame
    contributes one TranscriptSegment combining a VLM action-caption with
    that frame's OCR text — this flows through the exact same
    extract_recipe.call_llm() -> citation_map.map_steps_to_timestamps()
    pipeline as a real transcript afterward; Step.verbatim_transcript_citation
    just ends up citing synthesized text instead of spoken words. See
    orchestrator.py's narration guard for where this gets called."""
    timestamps = _sample_timestamps(
        duration_seconds, settings.vision_narration_max_frames, settings.vision_narration_min_interval_seconds
    )
    if not timestamps:
        return TranscriptResult(segments=[], source="vision")

    interval = timestamps[1] - timestamps[0] if len(timestamps) > 1 else duration_seconds
    segments: list[TranscriptSegment] = []

    # Sequential, not concurrent, deliberately: the VLM subprocess shares
    # tight Metal/Neural Engine memory headroom with Ollama's resident
    # Qwen2.5 7B (ollama_keep_alive=-1), so this never parallelizes VLM calls.
    for i, ts in enumerate(timestamps):
        frame_path = tmp_frames_dir / f"narration_{i}.jpg"
        try:
            await frames.extract_frame(video_path, ts, frame_path)
        except frames.FrameExtractionError as e:
            logger.warning("vision_narration: frame extraction failed at %.1fs: %s", ts, e)
            continue

        ocr_lines = await ocr.ocr_frame(frame_path)
        ocr_text = " ".join(ocr_lines)

        try:
            caption = await vlm.caption_frame_action(frame_path)
        except vlm.VlmError as e:
            logger.warning("vision_narration: captioning failed at %.1fs: %s", ts, e)
            caption = ""

        text = ". ".join(t for t in (caption, ocr_text) if t).strip()
        if not text:
            continue  # nothing usable from this frame — don't cite an empty segment

        segments.append(TranscriptSegment(text=text, start=ts, end=ts + interval))

    return TranscriptResult(segments=segments, source="vision")
