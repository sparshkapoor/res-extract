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
