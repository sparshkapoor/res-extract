import logging
import shutil

from app.cache import result_cache
from app.config import get_settings
from app.jobs import job_manager
from app.models import JobStatus, Platform, Recipe
from app.pipeline import (
    citation_map,
    download,
    extract_recipe,
    frames,
    ocr,
    spellcheck,
    transcript,
    vision_narration,
    vlm,
)
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

        # --- 4. Narration guard: fall back to vision if narration is too sparse ---
        # Below this bar, real narration can't be trusted on its own — but rather
        # than fail outright, synthesize a vision-grounded transcript (VLM action
        # captions + per-frame OCR, sampled across the video) and feed THAT through
        # the exact same downstream pipeline. See vision_narration.py.
        word_count = len(full_text.split())
        if len(full_text) < settings.empty_transcript_min_chars or word_count < settings.empty_transcript_min_words:
            await job_manager.update_status(
                job_id, JobStatus.transcribing, "No narration detected — analyzing video frames instead..."
            )
            vision_transcript = await vision_narration.build_vision_transcript(
                video_asset.video_path, video_asset.duration_seconds, job_frames_dir, settings
            )
            if not vision_transcript.segments:
                raise PipelineError(
                    "No narration and no usable visual content detected in this video."
                )
            transcript_result = (
                vision_transcript if word_count == 0 else transcript.merge(transcript_result, vision_transcript)
            )
            full_text = transcript_result.full_text
            await job_manager.update_status(
                job_id, JobStatus.transcribed,
                f"Transcript ready ({transcript_result.source}, {len(full_text)} chars)",
            )

        # --- 5. LLM pass 1: transcript -> Recipe ----------------------------
        await job_manager.update_status(job_id, JobStatus.extracting, "Extracting recipe via Qwen2.5...")
        recipe = await extract_recipe.call_llm(full_text, url, platform)
        recipe.title = recipe.title or video_asset.title

        if not recipe.steps:
            raise PipelineError("LLM extraction produced no recipe steps from this transcript.")

        # --- 5b. Refine ingredients with the video's own written description ---
        # Runs before OCR refinement so OCR only has to incrementally improve an
        # already-good list, not start from raw transcript-only extraction.
        # Ingredients have no citation requirement (unlike steps), so this
        # non-timestamped text is safe to use here the same way OCR text is.
        if video_asset.description.strip():
            await job_manager.update_status(
                job_id, JobStatus.extracting, "Refining ingredients from video description..."
            )
            recipe.ingredients = await extract_recipe.refine_ingredients_with_description(
                recipe.ingredients, video_asset.description
            )

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

        # --- 9c. Deterministic (non-LLM) spelling cleanup on step text ----------------
        # Complementary to 9b, not a replacement: the LLM proofread checks
        # citation-faithfulness; this catches literal misspellings (residual ASR
        # garble) the LLM had no particular reason to flag as suspicious.
        recipe.steps = spellcheck.clean_step_text(recipe.steps)

        # --- 10. VLM vision pass: ground still-estimated quantities AND still-generic ---
        # ingredient names (e.g. "spices") in the step photos. The identify task only
        # ever runs for ingredients still name_is_generic=true at this point — i.e.
        # description-refinement (5b) had a description to work with but didn't
        # resolve this one, or there was no description at all. (OCR-refinement at
        # step 9 is deliberately quantity/unit-only — it never renames ingredients,
        # see _build_pass2_prompt — so it can't have already resolved this.) This is
        # the last-resort visual fallback, after every text-based source has failed.
        if any(ing.is_estimated or ing.name_is_generic for ing in recipe.ingredients):
            await job_manager.update_status(job_id, JobStatus.ocr, "Estimating quantities from photos...")
            try:
                recipe = await vlm.refine_estimates_with_vision(recipe, job_frames_dir)
            except vlm.VlmError as e:
                # Vision refinement is a best-effort enrichment on top of the
                # text-only estimate already in hand — never fail the job over it.
                logger.warning("VLM quantity/identify refinement failed, keeping text-only estimates: %s", e)

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
