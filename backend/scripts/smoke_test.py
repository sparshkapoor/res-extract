"""Fast-iteration CLI: runs the full pipeline in-process for one URL,
bypassing HTTP/SSE entirely (no need to spin up uvicorn/Colima).

Usage: .venv/bin/python scripts/smoke_test.py <url> [--force]

--force clears any existing cache entry for this URL first, so you can
re-run the full pipeline against a URL you've already tested.
"""

import asyncio
import logging
import sys
import time
import uuid

# Not imported via app.main here (this bypasses HTTP entirely), so the
# per-stage [timing] logs in orchestrator.py need their own basicConfig call
# to actually be visible — mirrors app/main.py's setup.
logging.basicConfig(level=logging.INFO)

from app.cache import result_cache
from app.db import get_db, init_db
from app.jobs import job_manager
from app.pipeline import orchestrator, vlm
from app.pipeline.url_utils import detect_platform, normalize_url, sha256_of_url


async def main(url: str, force: bool) -> None:
    try:
        await init_db()
        url = normalize_url(url)
        platform = detect_platform(url)
        url_hash = sha256_of_url(url)

        if force:
            async with get_db() as db:
                await db.execute("DELETE FROM result_cache WHERE url_hash = ?", (url_hash,))
                await db.commit()
            print(f"[smoke_test] cleared cache entry for {url_hash}")

        job_id = str(uuid.uuid4())
        await job_manager.create_job(job_id, url, url_hash, platform.value)

        print(f"[smoke_test] job_id={job_id} platform={platform.value} url={url}")
        start = time.time()
        await orchestrator.run_pipeline(job_id, url)
        elapsed = time.time() - start

        job = await job_manager.get_job(job_id)
        print(f"\n[smoke_test] finished in {elapsed:.1f}s, status={job['status']}")
        if job["error"]:
            print(f"[smoke_test] error: {job['error']}")
            sys.exit(1)

        recipe = await result_cache.get_cached(url_hash)
        if recipe is None:
            print("[smoke_test] status=done but no cached recipe found — bug")
            sys.exit(1)

        print(f"\nTitle: {recipe.title}")
        print(f"Ingredients ({len(recipe.ingredients)}):")
        for ing in recipe.ingredients:
            print(f"  - {ing.quantity or ''} {ing.unit or ''} {ing.name}".strip())
        print(f"\nSteps ({len(recipe.steps)}):")
        for step in recipe.steps:
            print(f"  {step.index}. [{step.timestamp_seconds:.1f}s] {step.instruction}")
            print(f"     citation: {step.verbatim_transcript_citation!r}")
            print(f"     image: {step.image_path}")
    finally:
        # The VLM worker (WS5) is a long-lived subprocess now — this script
        # runs the pipeline in-process with no server around to shut it
        # down for us, so it must clean up after itself here.
        await vlm.shutdown()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: smoke_test.py <url> [--force]")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], "--force" in sys.argv))
