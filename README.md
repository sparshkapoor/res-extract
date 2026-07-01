# res-extract

Paste a YouTube Short or Instagram Reel of a cooking video and get back a
structured, step-by-step recipe: title, ingredients (with quantities —
stated, or estimated from the transcript and step photos when they aren't),
and steps each tied to a timestamp and a photo pulled from the video itself.
Every extraction is cached and browsable later in a Saved Recipes gallery.

## Why it's built this way

Apple Silicon has no IOMMU/SR-IOV, so a Docker/Colima Linux VM cannot reach
Metal, the GPU, or the Neural Engine. Every AI component here — the LLM, the
speech-to-text model, and the vision model — therefore runs **bare-metal on
macOS**, not in a container. Docker/Colima is used for exactly one thing:
an `nginx` reverse proxy in front of the bare-metal backend, which matters
on a headless deployment target where Docker Desktop (GUI-session
dependent) isn't viable but a CLI-only Lima VM is.

### Why these three models

Everything is sized around one constraint: it all has to fit, resident, in
the unified memory of a 16GB M1 Air — the actual deployment target, not a
theoretical one.

- **Qwen2.5 7B (via Ollama, `ollama_keep_alive=-1`)** — the text LLM that
  does structured recipe extraction. 7B is the largest text model that
  leaves headroom for the vision model to load *alongside* it later in the
  same pipeline run (see below) — a larger model would mean unloading and
  reloading between passes, which costs real wall-clock time on every
  single job. It's constrained to a JSON schema (`Recipe.model_json_schema()`
  passed straight to Ollama's `format=`) rather than free-text + parsing,
  so structural correctness (required fields, enum values) is guaranteed by
  construction, not hoped for.
- **mlx-whisper "small"** (not "large-v3") — ASR only runs when YouTube has
  no native captions, or on Instagram (which has no caption API at all). A
  larger Whisper checkpoint would transcribe more accurately, but "small"
  was chosen deliberately to leave memory room for Qwen2.5 7B to already be
  resident by the time ASR runs — the tradeoff is transcription accuracy
  for the ability to run the whole pipeline without swapping models in and
  out of memory. It runs in its own subprocess (`_asr_worker.py`-style
  isolation, same pattern as the VLM below) so its Metal allocation is
  fully released the moment it's done, rather than lingering for the rest
  of the job.
- **Qwen2.5-VL-3B-Instruct (4-bit, via mlx-vlm)** — the vision-language
  model, used for three distinct jobs that all share one subprocess/model
  load (`_vlm_worker.py`, task-tagged requests: `quantity` / `identify` /
  `narrate`): grounding an ingredient's estimated quantity in the actual
  step photo, identifying a specific spice/seasoning from a frame when the
  transcript only says "spices," and — for videos with too little narration
  to extract from — captioning what's happening in sampled frames to
  synthesize a usable transcript. 3B (not the larger 7B/32B VL variants) is
  the size that fits in the ~3.5GB of headroom left over once Qwen2.5 7B's
  ~5.5GB resident footprint and Whisper's already-released allocation are
  accounted for — see `config.py`'s inline comments for the exact memory
  math this was budgeted against.
- **Apple Vision (`ocrmac`)**, not a separate OCR model — it's free
  (built into macOS, no model weights, no extra memory budget) and
  genuinely accurate for the on-screen text overlays cooking videos
  actually use (ingredient callouts, oven temps). There was no reason to
  spend memory budget on a dedicated OCR model when the OS already ships
  one this capable.
- **`pyspellchecker`, deliberately not a fourth LLM pass** — a small,
  final, non-LLM cleanup pass over step text (see Pipeline step 10 below).
  Edit-distance dictionary correction is a few milliseconds; routing it
  through the LLM would mean another full Ollama round-trip per recipe for
  something a plain algorithm handles fine 95% of the time. It's
  deliberately conservative (see `spellcheck.py`) — it only corrects a
  word when the dictionary has a single unambiguous candidate, because
  plain frequency-based correction without context *will* occasionally
  "fix" a typo into a different, wrong, more-common word (e.g. "heet"
  being nearer to "meet" than "heat" by raw corpus frequency) — better to
  leave an obvious typo visible than confidently introduce a wrong word.

## Architecture

```
iPhone/PWA ──HTTP──▶ [Colima: nginx] ──proxy /api,/media──▶ [bare-metal: FastAPI/uvicorn :8000]
                                                                    │
                                                                    ├─▶ Ollama (Qwen2.5 7B, :11434, resident)
                                                                    ├─▶ mlx-whisper (subprocess, ASR)
                                                                    ├─▶ mlx-vlm (subprocess, Qwen2.5-VL-3B —
                                                                    │   one worker, 3 tasks: quantity/identify/narrate)
                                                                    ├─▶ ocrmac (Apple Vision OCR)
                                                                    └─▶ yt-dlp / ffmpeg
```

### Pipeline

1. **Cache check** — SHA-256 of the normalized URL; instant return on a repeat.
2. **Download** — `yt-dlp` (YouTube: no auth needed; Instagram: needs cookies, see below).
   Also captures the video's own written description/caption — yt-dlp
   normalizes both platforms' fields into one `description` key, used in
   step 5b below.
3. **Transcript** — YouTube tries native captions first (skips ASR entirely);
   Instagram and caption-less YouTube fall back to `mlx-whisper`, which runs
   in its own subprocess so its Metal memory is fully released afterward.
4. **Narration guard, with a vision fallback** — if the transcript is too
   short/sparse to trust (`empty_transcript_min_chars`/`_min_words` in
   `config.py`), the pipeline no longer fails outright. Instead
   `vision_narration.py` samples ~15-18 frames evenly across the video,
   captions each one's action with the VLM (`task="narrate"`) and runs OCR
   on it, and stitches the results into a *synthetic, timestamped
   transcript* — same shape (`TranscriptSegment(text, start, end)`) as a
   real one. If there was *some* real narration just under the threshold,
   it's blended with the synthetic segments (`transcript.merge`, sorted by
   time) rather than discarded. This synthetic/blended transcript then
   flows through every step below completely unchanged — steps still cite
   an exact substring of "the transcript," it just may now be a VLM
   sentence instead of a spoken one. This is intentionally the *only*
   silent-video accommodation: it doesn't invent a parallel data model, and
   the existing hallucination guard (step 6) still catches genuinely
   unusable video the same way it always did. It's also meaningfully
   slower than the narrated path (a batch of sequential VLM+OCR calls
   before the LLM even starts) — the job's status stream says
   "analyzing video frames instead..." so that latency isn't silent.
5. **Recipe extraction** — Qwen2.5 7B via Ollama, JSON-schema-constrained
   output, grouped into coherent steps (not one step per sentence). Also
   pulls cook time, servings, calories, and oven temperature when stated
   or clearly implied — left blank rather than guessed, unlike ingredient
   quantities. Generic ingredient references ("spices", "seasoning") are
   named as the plain category word with `name_is_generic=true` set —
   never as an invented placeholder like "spices (not specified)".
5b. **Ingredient refinement from the video's description** — if the video
    has a written description, a second LLM pass treats it as more
    authoritative than spoken narration for ingredient names/quantities
    (creators write these down precisely). Unlike every other refinement
    pass, this one is *allowed* to change the ingredient count: a generic
    ingredient with a description that itemizes it (e.g. "Spices: 1 tsp
    salt, 1 tsp black pepper, 1 tsp cinnamon...") gets split into one
    `Ingredient` per item, each with a real stated quantity. Ingredients
    have no citation requirement (unlike steps), so this non-timestamped
    text is safe to use here the same way OCR text is used in step 9.
6. **Citation → timestamp mapping** — each step cites a real transcript
   substring; that's matched back to a timestamp, with a fuzzy fallback and
   monotonicity enforcement (steps can't jump backward in time). If every
   single step fails to match, the job fails rather than returning a
   fabricated recipe — this is what actually catches a garbage/hallucinated
   extraction, whether the underlying transcript was spoken, synthetic, or
   blended.
7. **Frame extraction** — one `ffmpeg` grab per step.
8. **OCR** — Apple Vision (`ocrmac`) on each frame, for on-screen text
   (measurements, ingredients) that was never spoken aloud.
9. **Ingredient refinement from OCR** — a narrowly-scoped LLM pass that
   touches *only* ingredient quantities/units for ingredients that already
   have a name, never steps and never ingredient identity (an earlier
   version let it rewrite steps too, which caused instruction/citation
   misalignment on longer recipes).
10. **Step proofreading + spelling cleanup** — an LLM pass checks each
    instruction against its own citation and fixes anything garbled,
    without touching citations/timestamps/images; then a deterministic,
    non-LLM spellcheck pass (`spellcheck.py`, `pyspellchecker`) catches
    residual literal typos the LLM had no reason to flag as suspicious.
11. **Vision-grounded quantity estimation + spice identification** — for
    any ingredient still without a real quantity, Qwen2.5-VL looks at the
    relevant step's photo and estimates one (`task="quantity"`, clearly
    marked as an estimate in the UI). Separately, for any ingredient still
    `name_is_generic=true` after steps 5b and 9 — i.e. no description and
    no useful OCR resolved it — the same VLM call batch also tries to
    identify the specific spice/seasoning shown (`task="identify"`,
    confidence-gated: an unclear/low-confidence result just keeps the
    plain generic name rather than guessing). Both tasks share one
    subprocess/model load, not two.
12. **Cache write + cleanup** — recipe and frames persisted; the downloaded
    video/audio are deleted (they're not needed once cached).

## Repo layout

```
backend/            FastAPI app, pipeline modules, tests
  app/
    pipeline/        download, transcript, asr, ocr, frames, vlm, vision_narration,
                      spellcheck, culinary_terms, extract_recipe, citation_map, orchestrator
    api/             submit / SSE status / result+saved-recipes routes
    jobs/, cache/    in-memory SSE broadcast + SQLite-backed job & result state
  scripts/           check_python_env.py, smoke_test.py (run the pipeline without HTTP)
  tests/             pytest unit tests
frontend/            Vite + React + TS + Tailwind v4 PWA
  DESIGN.md           literal design-system spec — dark canvas, Linear-style precision
                       chrome vs. genuine glass on photo-backed cards, Fraunces editorial
                       headlines vs. Inter/JetBrains-Mono functional chrome, motion tokens
  src/components/     UrlSubmitForm, ProgressView, RecipeCard, StepCard, SavedRecipesList
  src/hooks/           useHeroScrollReveal, useScrollReveal (GSAP ScrollTrigger)
  src/lib/             gsap.ts (plugin registration + reduced-motion guard), motion.ts
deploy/
  colima/             nginx.conf + docker-compose.yml (nginx only — see comments for why)
  launchd/            backend launchd plist for the headless M1 Air
  README.md           full deployment steps
```

## Running it locally

### Prerequisites

```bash
brew install ffmpeg yt-dlp colima
ollama pull qwen2.5:7b
```

### Backend

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/check_python_env.py   # verifies mlx/mlx-whisper/mlx-vlm/ocrmac all import cleanly
OLLAMA_KEEP_ALIVE=-1 ollama serve &            # if not already running
PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload --port 8000
```

Fast iteration without HTTP: `PYTHONPATH=. .venv/bin/python scripts/smoke_test.py "<video-url>" --force`

### Frontend

```bash
cd frontend
npm install
npm run dev   # proxies /api and /media to localhost:8000, see vite.config.ts
```

### Tests

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/ -v
```

## Instagram Reels

Instagram requires an authenticated session even for public reels — yt-dlp's
plain HTTP requests get blocked by their anti-bot detection. Export cookies
from a logged-in browser:

```bash
yt-dlp --cookies-from-browser firefox --cookies backend/storage/instagram_cookies.txt --skip-download "<reel-url>"
```

Then set `INSTAGRAM_COOKIES_FILE` in `backend/.env` (see `.env.example`) to
that path. Cookies expire — re-export when downloads start failing with an
auth error.

## Deploying to the headless M1 Air

See [`deploy/README.md`](deploy/README.md) for the full walkthrough:
bare-metal Ollama + backend via launchd, Colima running only nginx,
frontend build, and moving Instagram cookies over.

## Known limitations

- **Ingredient quantities are estimated, not measured**, when a video never
  states them (text-only LLM guess, refined by a vision pass looking at the
  step photo). These are visually marked with `~` in the UI. They can be
  meaningfully off — compared against a real published recipe during
  testing, some estimates landed close, others were 2x off.
- **Silent/low-narration videos now get a best-effort extraction, not
  parity with a narrated one.** The vision-narration fallback (pipeline
  step 4) produces coarser steps than spoken narration would ("Mix
  ingredients in bowl" vs. a narrated "Whisk 2 eggs with 1/4 cup sugar
  until pale") — it's genuine enrichment over failing the job outright, not
  a substitute for real narration. It's also the slowest path through the
  pipeline (a batch of sequential VLM+OCR calls before the LLM stage even
  starts).
- **Frequency-based spellcheck occasionally can't distinguish two
  real-but-different words at the same edit distance** — deliberately
  tuned conservative (see `spellcheck.py`), so it leaves a typo visible
  rather than risk silently swapping in a wrong-but-common word, but that
  means some genuine typos won't get auto-fixed.
- **TikTok and other platforms aren't supported** — only YouTube and
  Instagram, per the original scope decision.
- **No forced phoneme alignment or scene-detection frame scoring** —
  timestamps come from citation-matching against ASR/caption/synthetic
  segments, and frames are a single `ffmpeg` grab per step, not the
  sharpest of a burst. Source video itself is frequently only 360p-ish
  (whatever YouTube Shorts/Instagram Reels deliver) — there's no
  higher-resolution source to re-extract from, and the frontend hero
  deliberately matches the source's portrait aspect ratio and picks the
  last (usually plated/steadier) frame rather than the first, to avoid
  making that ceiling worse than it has to be.
- **LaunchAgents require an active GUI/loginwindow session** (`gui/<uid>`
  launchd domain) — pure SSH access doesn't create one. Verified on a real
  deployment that a LaunchDaemon (system-wide, no session needed) works
  fine instead, including OCR, which was the open question here. See
  `deploy/README.md` for both paths.
- **Colima's virtiofs mount type doesn't reliably bind-mount individual
  files** (directories are fine) — config files that need mounting into a
  container should be baked in at image-build time instead, not
  runtime-mounted.
