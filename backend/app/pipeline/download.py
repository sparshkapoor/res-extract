import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app.config import get_settings
from app.models import Platform

_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 2.0


class DownloadError(RuntimeError):
    pass


@dataclass
class VideoAsset:
    video_path: Path
    duration_seconds: float
    platform: Platform
    title: str
    description: str


def _download_sync(url: str, platform: Platform, out_dir: Path) -> VideoAsset:
    settings = get_settings()
    out_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts: dict = {
        "outtmpl": str(out_dir / "video.%(ext)s"),
        "format": "mp4/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    if platform == Platform.instagram:
        # Instagram requires an authenticated session for most reels; the
        # cookie file must be exported ahead of time from a logged-in
        # browser (see deploy notes — this machine has no GUI session).
        if settings.instagram_cookies_file is None or not settings.instagram_cookies_file.exists():
            raise DownloadError(
                "Instagram downloads require INSTAGRAM_COOKIES_FILE to be set to a valid "
                "cookies.txt exported from a logged-in browser session."
            )
        ydl_opts["cookiefile"] = str(settings.instagram_cookies_file)

    # yt-dlp's JS-challenge solving (invoked as a `deno` subprocess per
    # request) has observed intermittent flakiness under concurrent use:
    # extract_info() returns "successfully" with zero formats downloaded and
    # no file written, without raising. Retry a few times before giving up.
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        for stale in out_dir.glob("video.*"):
            stale.unlink()

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as e:
            last_error = e
            time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
            continue

        video_path = out_dir / "video.mp4"
        if not video_path.exists():
            # merge_output_format should guarantee mp4, but fall back to
            # whatever extension yt-dlp actually produced.
            candidates = list(out_dir.glob("video.*"))
            if candidates:
                video_path = candidates[0]
            else:
                last_error = DownloadError(
                    f"yt-dlp reported success but no output file found in {out_dir} "
                    f"(attempt {attempt}/{_MAX_ATTEMPTS})"
                )
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
                continue

        return VideoAsset(
            video_path=video_path,
            duration_seconds=float(info.get("duration") or 0.0),
            platform=platform,
            title=info.get("title") or "Untitled recipe",
            # yt-dlp normalizes each site's extractor-specific field (Instagram's
            # caption text, YouTube's video description) into this same key — no
            # per-platform branching needed, and no extra network call since it's
            # already part of the same extract_info() response.
            description=info.get("description") or "",
        )

    raise DownloadError(f"yt-dlp failed to download {url} after {_MAX_ATTEMPTS} attempts: {last_error}")


async def fetch_video(url: str, platform: Platform, out_dir: Path) -> VideoAsset:
    return await asyncio.to_thread(_download_sync, url, platform, out_dir)
