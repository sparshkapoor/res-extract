import asyncio
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.models import TranscriptResult, TranscriptSegment

_WORKER_SCRIPT = Path(__file__).parent / "_asr_worker.py"


class AsrError(RuntimeError):
    pass


async def transcribe(audio_path: Path) -> TranscriptResult:
    """Run mlx-whisper in a subprocess (see _asr_worker.py for why) and
    return the resulting segments. The subprocess exiting is what
    guarantees the model's Metal memory is fully freed before the caller
    proceeds to the Ollama LLM call."""
    settings = get_settings()

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(_WORKER_SCRIPT),
        str(audio_path),
        settings.asr_model_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise AsrError(f"mlx-whisper subprocess failed: {stderr.decode(errors='replace')[-2000:]}")

    try:
        # mlx-whisper/mlx may print progress noise to stdout; the JSON is the
        # last line.
        last_line = stdout.decode(errors="replace").strip().splitlines()[-1]
        data = json.loads(last_line)
    except (IndexError, json.JSONDecodeError) as e:
        raise AsrError(f"Could not parse ASR worker output: {stdout.decode(errors='replace')[-2000:]}") from e

    segments = [TranscriptSegment(**seg) for seg in data["segments"]]
    return TranscriptResult(segments=segments, source="asr")
