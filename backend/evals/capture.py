"""Bootstrap a golden case from a live URL: runs the real download +
transcript stages (yt-dlp, native captions or mlx-whisper) to freeze the
transcript/description exactly as the real pipeline would see them, then
writes evals/golden/<id>.json.

`expected` is prefilled from this URL's existing result_cache entry, if
one exists — a starting point to hand-correct, not a finished golden case.
Always review the written file before trusting it (see evals/README.md).

Usage:
    PYTHONPATH=. .venv/bin/python evals/capture.py <url> --id <slug>
"""

import argparse
import asyncio
import shutil
import sys
import uuid
from pathlib import Path

from app.cache import result_cache
from app.config import get_settings
from app.db import init_db
from app.models import Platform
from app.pipeline import comments as comments_pipeline
from app.pipeline import download, transcript
from app.pipeline.url_utils import detect_platform, normalize_url, sha256_of_url

from evals.schema import Expected, ExpectedIngredient, GoldenCase

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


async def _prefill_expected(url_hash: str) -> Expected:
    cached = await result_cache.get_cached(url_hash)
    if cached is None:
        return Expected()
    title_words = cached.title.split()
    return Expected(
        title_contains=[" ".join(title_words[:2])] if title_words else [],
        ingredients=[
            ExpectedIngredient(name=i.name, quantity=i.quantity, unit=i.unit) for i in cached.ingredients
        ],
        steps_count_range=(max(1, len(cached.steps) - 2), len(cached.steps) + 2),
    )


async def main(url: str, case_id: str, overwrite: bool, with_comments: bool) -> None:
    await init_db()
    out_path = GOLDEN_DIR / f"{case_id}.json"
    if out_path.exists() and not overwrite:
        print(f"[capture] {out_path} already exists — pass --overwrite to replace it")
        sys.exit(1)

    url = normalize_url(url)
    platform = detect_platform(url)
    url_hash = sha256_of_url(url)

    settings = get_settings()
    tmp_dir = settings.downloads_dir / f"capture-{uuid.uuid4()}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        print(f"[capture] downloading {url} ({platform.value})...")
        video_asset = await download.fetch_video(url, platform, tmp_dir)

        print("[capture] getting transcript (captions or ASR)...")
        transcript_result = await transcript.get_transcript(url, platform, video_asset.video_path, tmp_dir)

        print("[capture] checking result_cache for an expected-block starting point...")
        expected = await _prefill_expected(url_hash)

        case_comments: list[str] = []
        if with_comments:
            if platform != Platform.youtube:
                print("[capture] --with-comments skipped: comment scraping is YouTube-only")
            else:
                print("[capture] fetching comments...")
                settings = get_settings()
                fetched = await comments_pipeline.fetch_top_comments(
                    url, max_comments=settings.comment_mining_max_comments
                )
                case_comments = [c.text for c in fetched]
                print(f"[capture] captured {len(case_comments)} comments")

        case = GoldenCase(
            id=case_id,
            url=url,
            platform=platform,
            transcript=transcript_result,
            description=video_asset.description,
            ocr_text="",
            comments=case_comments,
            duration_seconds=video_asset.duration_seconds,
            expected=expected,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(case.model_dump_json(indent=2) + "\n")
    print(f"[capture] wrote {out_path}")
    print("[capture] `expected` was prefilled from the cache (if any) — hand-review it before relying on this case.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("--id", required=True, dest="case_id", help="golden case slug, e.g. 'rye-pitas'")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--with-comments", action="store_true",
        help="also fetch and freeze the video's top comments (YouTube only; see comments.py)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.url, args.case_id, args.overwrite, args.with_comments))
