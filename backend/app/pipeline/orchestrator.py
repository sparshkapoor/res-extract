import asyncio
import logging
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from app.cache import result_cache
from app.config import get_settings
from app.jobs import job_manager
from app.models import JobStatus, Platform, Recipe, TranscriptResult
from app.pipeline import (
    citation_map,
    download,
    extract_recipe,
    frames,
    normalize,
    ocr,
    spellcheck,
    transcript,
    validate,
    vision_narration,
    vlm,
)
from app.pipeline.url_utils import detect_platform, normalize_url, sha256_of_url

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    pass


def _nudge_forward(ts: float, last_ts: float, min_gap: float = 1.5) -> float:
    """Pushes `ts` forward when it would collide with or fall behind
    `last_ts` — used only for frame-*extraction* timestamps (see step 7),
    never citation_map.py's own timestamp semantics. Two steps whose
    citations both clamp to the same transcript moment would otherwise grab
    the identical video frame."""
    return ts if ts > last_ts else last_ts + min_gap


@asynccontextmanager
async def _timed_stage(name: str):
    """Cheap per-stage wall-clock logging — turns "it feels slow" into real
    per-stage numbers instead of guessing which part of the pipeline to
    optimize next."""
    start = time.monotonic()
    try:
        yield
    finally:
        logger.info("[timing] %s: %.1fs", name, time.monotonic() - start)


async def run_pipeline(job_id: str, raw_url: str) -> None:
    settings = get_settings()
    url = normalize_url(raw_url)
    platform = detect_platform(url)

    job_downloads_dir = settings.downloads_dir / job_id
    job_frames_dir = settings.frames_dir / job_id

    try:
        # --- 2. Download -------------------------------------------------
        await job_manager.update_status(job_id, JobStatus.downloading, "Downloading video via yt-dlp...")
        async with _timed_stage("download"):
            video_asset = await download.fetch_video(url, platform, job_downloads_dir)
        await job_manager.update_status(job_id, JobStatus.downloaded, f"Downloaded: {video_asset.title}")

        # --- 3. Transcript (captions-or-ASR branch) -----------------------
        await job_manager.update_status(
            job_id, JobStatus.transcribing,
            "Fetching captions..." if platform == Platform.youtube else "Running ASR (mlx-whisper)...",
        )
        async with _timed_stage("transcript"):
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
            async with _timed_stage("vision_narration"):
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

        # --- 4b. Transcript compaction + token budgeting ---------------------
        # Segment-level, not string-level: a citation the LLM copies verbatim
        # must stay a valid substring for citation_map below, so compaction
        # only drops/merges whole segments, never rewrites text inside one
        # that survives. The SAME compacted+budgeted segments feed both the
        # LLM (via full_text) and citation_map further down, so the
        # hallucination guard never sees a transcript the LLM didn't.
        compacted_segments = transcript.compact_segments(transcript_result.segments)
        budget_tokens = int(settings.ollama_num_ctx * 0.75) - extract_recipe.PASS1_PROMPT_OVERHEAD_TOKENS
        budgeted_segments, truncated = transcript.budget_segments(compacted_segments, budget_tokens)
        if truncated:
            # Rare (pathologically long transcripts) — makes today's silent
            # Ollama truncation past num_ctx into an observable event instead.
            logger.warning(
                "job %s: transcript truncated to fit token budget (%d -> %d segments)",
                job_id, len(compacted_segments), len(budgeted_segments),
            )
        transcript_result = TranscriptResult(segments=budgeted_segments, source=transcript_result.source)
        full_text = transcript_result.full_text

        # --- 5. LLM pass 1: transcript -> Recipe ----------------------------
        await job_manager.update_status(job_id, JobStatus.extracting, "Extracting recipe via Qwen2.5...")
        async with _timed_stage("llm_pass1_extract"):
            recipe = await extract_recipe.call_llm(full_text, url, platform)
        recipe.title = recipe.title or video_asset.title

        if not recipe.steps:
            raise PipelineError("LLM extraction produced no recipe steps from this transcript.")

        # --- 5a. Citation -> timestamp mapping ---------------------------------
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

        # --- 5b. Step-granularity validation + bounded corrective retry --------
        # Deterministic checks the citation guard above can't catch (a single
        # terse-but-cited step passes that guard fine) — see validate.py. Runs
        # before frame extraction/OCR/VLM so a retry never wastes that work.
        validation = validate.validate_recipe(recipe, transcript_result.segments, video_asset.duration_seconds)
        if validation.needs_retry:
            logger.info(
                "job %s: step-granularity validation flagged pass 1 (steps=%d, expected_min=%d, "
                "terse=%s, coverage=%.2f) — retrying once",
                job_id, len(recipe.steps), validation.expected_min_steps,
                validation.terse_step_indexes, validation.transcript_coverage,
            )
            corrective_note = validate.build_corrective_note(recipe, validation, video_asset.duration_seconds)
            async with _timed_stage("llm_pass1_retry"):
                retry_recipe = await extract_recipe.call_llm(
                    full_text, url, platform, corrective_note=corrective_note
                )
            if retry_recipe.steps:
                retry_recipe.title = retry_recipe.title or video_asset.title
                retry_recipe.steps, _retry_unmatched = citation_map.map_steps_to_timestamps(
                    retry_recipe.steps, transcript_result.segments, video_asset.duration_seconds
                )
                retry_validation = validate.validate_recipe(
                    retry_recipe, transcript_result.segments, video_asset.duration_seconds
                )
                # Coverage alone decides the winner: a garbage retry (e.g. the
                # model hallucinated on the corrective prompt) naturally scores
                # near-zero coverage, so this doubles as the retry's own sanity
                # check without a separate unmatched-citation guard.
                if retry_validation.transcript_coverage > validation.transcript_coverage:
                    logger.info(
                        "job %s: retry improved coverage %.2f -> %.2f, keeping retry",
                        job_id, validation.transcript_coverage, retry_validation.transcript_coverage,
                    )
                    recipe, validation = retry_recipe, retry_validation
                else:
                    logger.info(
                        "job %s: retry did not improve coverage (%.2f vs %.2f), keeping original attempt",
                        job_id, retry_validation.transcript_coverage, validation.transcript_coverage,
                    )
            else:
                logger.info("job %s: retry produced no steps, keeping original attempt", job_id)

        # --- 5c. Refine ingredients with the video's own written description ---
        # Runs before OCR refinement so OCR only has to incrementally improve an
        # already-good list, not start from raw transcript-only extraction.
        # Ingredients have no citation requirement (unlike steps), so this
        # non-timestamped text is safe to use here the same way OCR text is.
        if video_asset.description.strip():
            await job_manager.update_status(
                job_id, JobStatus.extracting, "Refining ingredients from video description..."
            )
            async with _timed_stage("llm_description_refine"):
                recipe.ingredients = await extract_recipe.refine_ingredients_with_description(
                    recipe.ingredients, video_asset.description
                )

        await job_manager.update_status(
            job_id, JobStatus.extracted, f"Extracted {len(recipe.steps)} steps, {len(recipe.ingredients)} ingredients"
        )

        # --- 7. Frame extraction per step ---------------------------------------
        await job_manager.update_status(job_id, JobStatus.extracting_frames, "Extracting step frames...")
        frame_paths: list = []
        # Nudge extraction timestamps forward when they'd collide with the
        # previous step's — citation_map.py's monotonicity clamp can leave two
        # steps with the *identical* timestamp_seconds (a citation that fuzzy-
        # matched earlier than intended gets clamped to exactly the prior
        # step's time), which otherwise grabs the same video frame for both.
        # Scoped to extraction only, not citation_map.py's own clamp — the
        # citation/timestamp semantics stay untouched (still load-bearing for
        # the hallucination guard above); this only fixes the visual symptom.
        last_extraction_ts = -1.0
        async with _timed_stage("frame_extraction"):
            for step in recipe.steps:
                ts = _nudge_forward((step.timestamp_seconds or 0.0) + 1.0, last_extraction_ts)
                last_extraction_ts = ts
                out_path = job_frames_dir / f"step_{step.index}.jpg"
                try:
                    await frames.extract_frame(video_asset.video_path, ts, out_path)
                    step.image_path = f"/media/jobs/{job_id}/{out_path.name}"
                    frame_paths.append(out_path)
                except frames.FrameExtractionError as e:
                    logger.warning("frame extraction failed for step %d: %s", step.index, e)
        await job_manager.update_status(job_id, JobStatus.frames_done, f"Extracted {len(frame_paths)} frames")

        # --- 7b. Hero-candidate frames ---------------------------------------------
        # Dedicated finished-dish candidates, independent of any step's timestamp —
        # step frames are inherently instructional moments (chopping, stirring, a
        # bite/reaction shot), never a reliable stand-in for "the finished dish".
        # Sampled near the start (common cold-open shot) and end (common outro/
        # plated shot) of the video; scored by the VLM in step 10 below.
        hero_candidate_paths: list[Path] = []
        duration = video_asset.duration_seconds
        if duration > 0:
            hero_timestamps = sorted(
                {
                    max(0.0, min(1.5, duration - 0.1)),
                    max(0.0, min(duration * 0.85, duration - 0.1)),
                    max(0.0, duration - 1.5),
                }
            )
            for i, ts in enumerate(hero_timestamps):
                out_path = job_frames_dir / f"hero_{i}.jpg"
                try:
                    await frames.extract_frame(video_asset.video_path, ts, out_path)
                    hero_candidate_paths.append(out_path)
                except frames.FrameExtractionError as e:
                    logger.warning("hero-candidate frame extraction failed at %.1fs: %s", ts, e)

        # --- 8. OCR per frame + dedupe -------------------------------------------
        await job_manager.update_status(job_id, JobStatus.ocr, "Running OCR on frames (Apple Vision)...")
        # Parallel, unlike the VLM/LLM calls elsewhere in this file — Apple
        # Vision OCR is a lightweight, stateless per-image call, not part of
        # the tight Metal/unified-memory budget the LLM/VLM share (see
        # config.py), so there's no contention risk to avoid here.
        async with _timed_stage("ocr"):
            per_frame_text = await asyncio.gather(*(ocr.ocr_frame(p) for p in frame_paths))
        ocr_text = ocr.dedupe_ocr_text(per_frame_text)

        # --- 9. LLM pass 2 (only if OCR found text) --------------------------------
        # Scoped to ingredients only — see extract_recipe._build_pass2_prompt for
        # why this must never touch steps (it used to, and on longer/complex
        # recipes the model would silently misalign instructions to citations).
        if ocr_text.strip():
            await job_manager.update_status(job_id, JobStatus.ocr, "Refining recipe with on-screen text...")
            async with _timed_stage("llm_ocr_refine"):
                recipe.ingredients = await extract_recipe.refine_ingredients_with_ocr(recipe.ingredients, ocr_text)

        # --- 9b. Proofread step instructions against their own citations -------------
        await job_manager.update_status(job_id, JobStatus.refining, "Proofreading steps...")
        async with _timed_stage("llm_proofread"):
            recipe.steps = await extract_recipe.proofread_steps(recipe.steps)

        # --- 9c. Deterministic (non-LLM) spelling cleanup on step text ----------------
        # Complementary to 9b, not a replacement: the LLM proofread checks
        # citation-faithfulness; this catches literal misspellings (residual ASR
        # garble) the LLM had no particular reason to flag as suspicious.
        await job_manager.update_status(job_id, JobStatus.refining, "Cleaning up spelling...")
        recipe.steps = spellcheck.clean_step_text(recipe.steps)

        # --- 10. VLM vision pass: hero-shot selection, plus grounding still- ---------
        # estimated quantities AND still-generic ingredient names (e.g. "spices") in
        # the step photos. Runs unconditionally now (hero selection always needs it),
        # with quantity/identify requests folded in when applicable — one subprocess/
        # model-load either way. The identify task only ever fires for ingredients
        # still name_is_generic=true at this point — i.e. description-refinement (5b)
        # had a description to work with but didn't resolve this one, or there was no
        # description at all. (OCR-refinement at step 9 is deliberately quantity/unit-
        # only — it never renames ingredients — so it can't have already resolved
        # this.) This is the last-resort visual fallback for ingredient identity,
        # after every text-based source has failed.
        await job_manager.update_status(job_id, JobStatus.refining, "Selecting hero photo, estimating quantities...")
        try:
            async with _timed_stage("vlm_refine"):
                recipe = await vlm.refine_estimates_with_vision(recipe, job_frames_dir, hero_candidate_paths)
        except vlm.VlmError as e:
            # Vision refinement is a best-effort enrichment on top of the
            # text-only estimate already in hand — never fail the job over it.
            logger.warning("VLM refinement failed, keeping text-only estimates and no hero shot: %s", e)

        if recipe.hero_image_path:
            recipe.hero_image_path = f"/media/jobs/{job_id}/{recipe.hero_image_path}"

        # --- 10.5. Deterministic ingredient/unit cleanup ----------------------------
        # Runs last, after every LLM/VLM pass has had a chance to fill in
        # quantity/unit/name — a single authoritative pass rather than
        # duplicated ad hoc cleanup in each pass. See normalize.py; also
        # reused verbatim by scripts/repair_cache.py and evals/metrics.py.
        async with _timed_stage("normalize"):
            recipe = normalize.normalize_recipe(recipe)

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
