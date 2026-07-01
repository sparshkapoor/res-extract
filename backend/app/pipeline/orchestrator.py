import logging
import shutil

from app.cache import result_cache
from app.config import get_settings
from app.jobs import job_manager
from app.models import JobStatus, Platform, Recipe
from app.pipeline import citation_map, download, extract_recipe, frames, ocr, transcript, vlm
from app.pipeline.url_utils import detect_platform, normalize_url, sha256_of_url

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    pass


async def run_pipeline(job_id: str, raw_url: str) -> None:
    settings = get_settings()
    url = normalize_url(raw_url)
    platform = detect_platform(url)

    job_downloads_dir = settings.downloads_dir / job_id
    job_frames_dir = settings.frames_dir / job_id

    try:
        # --- 2. Download -------------------------------------------------
        await job_manager.update_status(job_id, JobStatus.downloading, "Downloading video via yt-dlp...")
        video_asset = await download.fetch_video(url, platform, job_downloads_dir)
        await job_manager.update_status(job_id, JobStatus.downloaded, f"Downloaded: {video_asset.title}")

        # --- 3. Transcript (captions-or-ASR branch) -----------------------
        await job_manager.update_status(
            job_id, JobStatus.transcribing,
            "Fetching captions..." if platform == Platform.youtube else "Running ASR (mlx-whisper)...",
        )
        transcript_result = await transcript.get_transcript(
            url, platform, video_asset.video_path, job_downloads_dir
        )
        full_text = transcript_result.full_text
        await job_manager.update_status(
            job_id, JobStatus.transcribed,
            f"Transcript ready ({transcript_result.source}, {len(full_text)} chars)",
        )

        # --- 4. Empty-transcript guard -------------------------------------
        word_count = len(full_text.split())
        if len(full_text) < settings.empty_transcript_min_chars or word_count < settings.empty_transcript_min_words:
            raise PipelineError(
                "No narration detected — silent-cooking videos are out of scope for this MVP."
            )

        # --- 5. LLM pass 1: transcript -> Recipe ----------------------------
        await job_manager.update_status(job_id, JobStatus.extracting, "Extracting recipe via Qwen2.5...")
        recipe = await extract_recipe.call_llm(full_text, url, platform)
        recipe.title = recipe.title or video_asset.title

        if not recipe.steps:
            raise PipelineError("LLM extraction produced no recipe steps from this transcript.")

        # --- 6. Citation -> timestamp mapping ---------------------------------
        recipe.steps, unmatched_count = citation_map.map_steps_to_timestamps(
            recipe.steps, transcript_result.segments, video_asset.duration_seconds
        )
        if unmatched_count == len(recipe.steps):
            # Every single step's citation failed to match the real transcript —
            # a strong signal the LLM hallucinated the whole recipe from a
            # garbage/near-empty transcript (e.g. Whisper repetition-looping on
            # near-silent audio), rather than one-off citation drift on an
            # otherwise-valid extraction. Fail the job instead of returning
            # fabricated content as if it were a successful result.
            raise PipelineError(
                "LLM extraction could not be verified against the transcript — "
                "this video likely has insufficient narration for recipe extraction."
            )
        await job_manager.update_status(
            job_id, JobStatus.extracted, f"Extracted {len(recipe.steps)} steps, {len(recipe.ingredients)} ingredients"
        )

        # --- 7. Frame extraction per step ---------------------------------------
        await job_manager.update_status(job_id, JobStatus.extracting_frames, "Extracting step frames...")
        frame_paths: list = []
        for step in recipe.steps:
            ts = (step.timestamp_seconds or 0.0) + 1.0
            out_path = job_frames_dir / f"step_{step.index}.jpg"
            try:
                await frames.extract_frame(video_asset.video_path, ts, out_path)
                step.image_path = f"/media/jobs/{job_id}/{out_path.name}"
                frame_paths.append(out_path)
            except frames.FrameExtractionError as e:
                logger.warning("frame extraction failed for step %d: %s", step.index, e)
        await job_manager.update_status(job_id, JobStatus.frames_done, f"Extracted {len(frame_paths)} frames")

        # --- 8. OCR per frame + dedupe -------------------------------------------
        await job_manager.update_status(job_id, JobStatus.ocr, "Running OCR on frames (Apple Vision)...")
        per_frame_text = [await ocr.ocr_frame(p) for p in frame_paths]
        ocr_text = ocr.dedupe_ocr_text(per_frame_text)

        # --- 9. LLM pass 2 (only if OCR found text) --------------------------------
        # Scoped to ingredients only — see extract_recipe._build_pass2_prompt for
        # why this must never touch steps (it used to, and on longer/complex
        # recipes the model would silently misalign instructions to citations).
        if ocr_text.strip():
            await job_manager.update_status(job_id, JobStatus.ocr, "Refining recipe with on-screen text...")
            recipe.ingredients = await extract_recipe.refine_ingredients_with_ocr(recipe.ingredients, ocr_text)

        # --- 9b. Proofread step instructions against their own citations -------------
        await job_manager.update_status(job_id, JobStatus.extracted, "Proofreading steps...")
        recipe.steps = await extract_recipe.proofread_steps(recipe.steps)

        # --- 10. VLM vision pass: ground still-estimated quantities in the step photos ---
        if any(ing.is_estimated for ing in recipe.ingredients):
            await job_manager.update_status(job_id, JobStatus.ocr, "Estimating quantities from photos...")
            try:
                recipe = await vlm.refine_estimates_with_vision(recipe, job_frames_dir)
            except vlm.VlmError as e:
                # Vision refinement is a best-effort enrichment on top of the
                # text-only estimate already in hand — never fail the job over it.
                logger.warning("VLM quantity refinement failed, keeping text-only estimates: %s", e)

        # --- 11. Cache write -------------------------------------------------------
        url_hash = sha256_of_url(url)
        await result_cache.write_cache(url_hash, url, recipe, job_frames_dir)

        # --- 12. Disk cleanup --------------------------------------------------------
        # The source video/audio and the per-job frame copies are no longer
        # needed once the recipe + its frames are safely in the persistent
        # cache (storage/cache/{url_hash}/) — keeping them around just
        # burns disk for every video ever processed.
        shutil.rmtree(job_downloads_dir, ignore_errors=True)
        shutil.rmtree(job_frames_dir, ignore_errors=True)

    except PipelineError as e:
        await job_manager.update_status(job_id, JobStatus.failed, error=str(e))
        shutil.rmtree(job_downloads_dir, ignore_errors=True)
        shutil.rmtree(job_frames_dir, ignore_errors=True)
    except Exception as e:  # noqa: BLE001 - top-level pipeline guard
        logger.exception("pipeline failed for job %s", job_id)
        await job_manager.update_status(job_id, JobStatus.failed, error=f"Internal error: {e}")
        shutil.rmtree(job_downloads_dir, ignore_errors=True)
        shutil.rmtree(job_frames_dir, ignore_errors=True)
    else:
        await _finalize(job_id, recipe)


async def _finalize(job_id: str, recipe: Recipe) -> None:
    from app.db import get_db

    async with get_db() as db:
        url_hash = sha256_of_url(recipe.source_url)
        await db.execute(
            "UPDATE jobs SET result_cache_id = ? WHERE job_id = ?", (url_hash, job_id)
        )
        await db.commit()
    await job_manager.update_status(job_id, JobStatus.done, "Recipe extraction complete")
