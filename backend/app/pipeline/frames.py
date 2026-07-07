import asyncio
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


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


# --- Perceptual distinctness (WS4c) -----------------------------------------
# Cheap average-hash over a downscaled grayscale copy — no model, just
# Pillow (already a transitive dependency). Good enough to catch "this is
# visually the same shot as the last step" without needing real scene
# detection; not meant to be a general-purpose image-similarity metric.

_HASH_SIZE = 8


def _average_hash(path: Path) -> int:
    with Image.open(path) as img:
        pixels = list(img.convert("L").resize((_HASH_SIZE, _HASH_SIZE), Image.LANCZOS).get_flattened_data())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p >= avg:
            bits |= 1 << i
    return bits


def _hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


async def extract_distinct_frame(
    video_path: Path,
    timestamp_seconds: float,
    out_path: Path,
    previous_hash: int | None,
    *,
    max_timestamp: float,
    min_gap: float = 1.5,
    max_attempts: int = 4,
    min_distinct_distance: int = 6,
) -> tuple[Path, int]:
    """Extracts a frame at `timestamp_seconds`, then — only if there's a
    `previous_hash` (the prior step's frame) to compare against — checks
    whether it's a near-duplicate (average-hash Hamming distance below
    `min_distinct_distance`, out of a max of 64 for an 8x8 hash). If so,
    retries at `timestamp_seconds + min_gap`, `+2*min_gap`, ... up to
    `max_attempts` times, never searching past `max_timestamp` (the next
    step's own timestamp, or video end) — accepts the least-similar
    candidate found if every attempt is still a near-duplicate. Never fails
    the job over this — a genuine ffmpeg failure still raises
    `FrameExtractionError` exactly as `extract_frame` would; only "every
    candidate was too similar" is swallowed (logged instead).

    Returns `(out_path, this frame's hash)` so callers can chain
    comparisons across consecutive steps."""
    candidates: list[tuple[Path, int, int | None]] = []
    tmp_paths: list[Path] = []
    try:
        for attempt in range(max_attempts):
            ts = min(timestamp_seconds + attempt * min_gap, max(timestamp_seconds, max_timestamp))
            tmp_path = out_path.with_name(f"{out_path.stem}__attempt{attempt}{out_path.suffix}")
            tmp_paths.append(tmp_path)
            await extract_frame(video_path, ts, tmp_path)
            this_hash = _average_hash(tmp_path)
            distance = _hamming_distance(this_hash, previous_hash) if previous_hash is not None else None
            candidates.append((tmp_path, this_hash, distance))
            if distance is None or distance >= min_distinct_distance or ts >= max_timestamp:
                break

        best_path, best_hash, best_distance = max(
            candidates, key=lambda c: c[2] if c[2] is not None else float("inf")
        )
        if len(candidates) > 1:
            if best_distance is not None and best_distance < min_distinct_distance:
                logger.warning(
                    "frames: still near-duplicate after %d attempts near %.1fs "
                    "(best Hamming distance %d/64) — using least-similar candidate found",
                    len(candidates), timestamp_seconds, best_distance,
                )
            else:
                logger.info(
                    "frames: retried %d time(s) near %.1fs to avoid a near-duplicate frame",
                    len(candidates) - 1, timestamp_seconds,
                )
        best_path.replace(out_path)
        return out_path, best_hash
    finally:
        for p in tmp_paths:
            p.unlink(missing_ok=True)  # the winning path was already moved via replace()
