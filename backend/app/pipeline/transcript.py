import asyncio
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

from app.models import Platform, TranscriptResult, TranscriptSegment
from app.pipeline import asr


class TranscriptError(RuntimeError):
    pass


def _extract_youtube_video_id(url: str) -> str | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == "youtu.be":
        return parts.path.strip("/").split("/")[0] or None
    if "youtube.com" in host:
        qs = parse_qs(parts.query)
        if "v" in qs:
            return qs["v"][0]
        m = re.search(r"/shorts/([^/?]+)", parts.path)
        if m:
            return m.group(1)
    return None


async def _get_youtube_captions(url: str) -> TranscriptResult | None:
    video_id = _extract_youtube_video_id(url)
    if video_id is None:
        return None

    def _fetch() -> TranscriptResult | None:
        try:
            fetched = YouTubeTranscriptApi().fetch(video_id)
        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
            return None
        segments = [
            TranscriptSegment(text=s.text, start=s.start, end=s.start + s.duration) for s in fetched
        ]
        return TranscriptResult(segments=segments, source="captions")

    return await asyncio.to_thread(_fetch)


async def _extract_audio(video_path: Path, out_dir: Path) -> Path:
    audio_path = out_dir / "audio.wav"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", str(video_path),
        "-ar", "16000", "-ac", "1", "-vn", str(audio_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise TranscriptError(f"ffmpeg audio extraction failed: {stderr.decode(errors='replace')[-1000:]}")
    return audio_path


async def get_transcript(url: str, platform: Platform, video_path: Path, out_dir: Path) -> TranscriptResult:
    """YouTube: try native captions first (skips ASR compute entirely).
    Instagram has no native-caption API, so it always goes through ASR."""
    if platform == Platform.youtube:
        captions = await _get_youtube_captions(url)
        if captions is not None and captions.segments:
            return captions

    audio_path = await _extract_audio(video_path, out_dir)
    return await asr.transcribe(audio_path)


def merge(real: TranscriptResult, vision: TranscriptResult) -> TranscriptResult:
    """Blend real (sparse but non-empty) narration with a synthesized vision
    transcript, sorted by start time. Used when the real transcript has *some*
    content but not enough to clear the empty-transcript guard on its own —
    see orchestrator.py's narration-guard block. `source="blended"` so the
    job's stage message and cached result stay honest about provenance."""
    segments = sorted([*real.segments, *vision.segments], key=lambda s: s.start)
    return TranscriptResult(segments=segments, source="blended")


# --- Compaction & token budgeting (WS4) -----------------------------------
# Segment-level, not string-level: citation_map.py needs the exact same
# segments the LLM saw, or a verbatim citation the model copied could stop
# resolving to a timestamp. Both compact_segments() and budget_segments()
# only ever drop/merge whole segments, never rewrite text inside one that
# survives, so a citation the LLM produces from surviving text stays a valid
# substring.

_FILLER_PATTERN = re.compile(r"^[\[\(].*[\]\)]$|^[♪\s]+$")
_MICRO_SEGMENT_MAX_WORDS = 3


def compact_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """Drops filler/no-op segments and merges runs of consecutive
    micro-segments (Whisper's tendency to split a short phrase into several
    tiny segments) into one, preserving the run's start/end timestamps.
    Idempotent: re-running on an already-compacted list is a no-op."""
    deduped: list[TranscriptSegment] = []
    for seg in segments:
        text = seg.text.strip()
        if not text or _FILLER_PATTERN.match(text):
            continue
        # Drop exact consecutive duplicates (Whisper repetition-looping on
        # near-silent/noisy audio produces runs of the identical segment).
        if deduped and deduped[-1].text.strip().lower() == text.lower():
            continue
        deduped.append(seg)

    merged: list[TranscriptSegment] = []
    for seg in deduped:
        text = seg.text.strip()
        is_micro = len(text.split()) < _MICRO_SEGMENT_MAX_WORDS
        if is_micro and merged:
            prev = merged[-1]
            merged[-1] = TranscriptSegment(
                text=f"{prev.text.strip()} {text}".strip(), start=prev.start, end=seg.end
            )
        else:
            merged.append(TranscriptSegment(text=text, start=seg.start, end=seg.end))
    return merged


def estimate_tokens(text: str) -> int:
    """Cheap chars/3.5 heuristic — good enough to catch pathological cases
    (multi-hour transcripts) before Ollama silently truncates past
    num_ctx; not meant to match a real tokenizer exactly."""
    return int(len(text) / 3.5)


def budget_segments(segments: list[TranscriptSegment], max_tokens: int) -> tuple[list[TranscriptSegment], bool]:
    """Drops whole segments from the tail until the joined transcript text
    fits max_tokens. Returns (possibly-truncated segments, whether any
    truncation happened) so the caller can log an observable warning instead
    of relying on Ollama's silent truncation past num_ctx."""
    full_text = " ".join(s.text.strip() for s in segments).strip()
    if estimate_tokens(full_text) <= max_tokens or not segments:
        return segments, False

    kept = list(segments)
    while len(kept) > 1:
        kept.pop()
        text = " ".join(s.text.strip() for s in kept).strip()
        if estimate_tokens(text) <= max_tokens:
            break
    return kept, True
