import asyncio
from pathlib import Path


class FrameExtractionError(RuntimeError):
    pass


async def extract_frame(video_path: Path, timestamp_seconds: float, out_path: Path) -> Path:
    """Single ffmpeg grab at the given timestamp. No scene detection or
    blur filtering — deliberately simple for MVP (deferred per plan)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-ss", f"{max(timestamp_seconds, 0):.3f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(out_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not out_path.exists():
        raise FrameExtractionError(
            f"ffmpeg frame extraction failed at {timestamp_seconds}s: {stderr.decode(errors='replace')[-1000:]}"
        )
    return out_path
