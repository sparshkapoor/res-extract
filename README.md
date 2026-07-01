# res-extract

Paste a YouTube Short or Instagram Reel of a cooking video and get back a
structured, step-by-step recipe: title, ingredients (with quantities —
stated, or estimated from the transcript and step photos when they aren't),
and steps each tied to a timestamp and a photo pulled from the video itself.

## Why it's built this way

Apple Silicon has no IOMMU/SR-IOV, so a Docker/Colima Linux VM cannot reach
Metal, the GPU, or the Neural Engine. Every AI component here — the LLM, the
speech-to-text model, and the vision model — therefore runs **bare-metal on
macOS**, not in a container. Docker/Colima is used for exactly one thing:
an `nginx` reverse proxy in front of the bare-metal backend, which matters
on a headless deployment target where Docker Desktop (GUI-session
dependent) isn't viable but a CLI-only Lima VM is.

## Architecture

```
iPhone/PWA ──HTTP──▶ [Colima: nginx] ──proxy /api,/media──▶ [bare-metal: FastAPI/uvicorn :8000]
                                                                    │
                                                                    ├─▶ Ollama (Qwen2.5 7B, :11434, resident)
                                                                    ├─▶ mlx-whisper (subprocess, ASR)
                                                                    ├─▶ mlx-vlm (subprocess, Qwen2.5-VL-3B)
                                                                    ├─▶ ocrmac (Apple Vision OCR)
                                                                    └─▶ yt-dlp / ffmpeg
```

### Pipeline

1. **Cache check** — SHA-256 of the normalized URL; instant return on a repeat.
2. **Download** — `yt-dlp` (YouTube: no auth needed; Instagram: needs cookies, see below).
3. **Transcript** — YouTube tries native captions first (skips ASR entirely);
   Instagram and caption-less YouTube fall back to `mlx-whisper`, which runs
   in its own subprocess so its Metal memory is fully released afterward.
4. **Empty-transcript guard** — bails out cleanly if there's no real narration
   (silent/ASMR cooking videos are out of scope), rather than sending
   near-empty input to the LLM.
5. **Recipe extraction** — Qwen2.5 7B via Ollama, JSON-schema-constrained
   output, grouped into coherent steps (not one step per sentence).
6. **Citation → timestamp mapping** — each step cites a real transcript
   substring; that's matched back to a timestamp, with a fuzzy fallback and
   monotonicity enforcement (steps can't jump backward in time).
7. **Frame extraction** — one `ffmpeg` grab per step.
8. **OCR** — Apple Vision (`ocrmac`) on each frame, for on-screen text
   (measurements, ingredients) that was never spoken aloud.
9. **Ingredient refinement from OCR** — a second, narrowly-scoped LLM pass
   that touches *only* ingredient quantities, never steps (an earlier
   version let it rewrite steps too, which caused instruction/citation
   misalignment on longer recipes).
10. **Step proofreading** — a third LLM pass checks each instruction against
    its own citation and fixes anything garbled, without touching
    citations/timestamps/images.
11. **Vision-grounded quantity estimation** — for any ingredient still
    without a real quantity, Qwen2.5-VL looks at the relevant step's photo
    and estimates one (clearly marked as an estimate in the UI).
12. **Cache write + cleanup** — recipe and frames persisted; the downloaded
    video/audio are deleted (they're not needed once cached).

## Repo layout

```
backend/            FastAPI app, pipeline modules, tests
  app/
    pipeline/        download, transcript, asr, ocr, frames, vlm, extract_recipe, orchestrator
    api/             submit / SSE status / result+saved-recipes routes
    jobs/, cache/    in-memory SSE broadcast + SQLite-backed job & result state
  scripts/           check_python_env.py, smoke_test.py (run the pipeline without HTTP)
  tests/             pytest unit tests
frontend/            Vite + React + TS + Tailwind v4 PWA
  DESIGN.md           Apple design tokens (from `getdesign`)
  src/components/     UrlSubmitForm, ProgressView, RecipeCard, StepCard, SavedRecipesList
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
- **TikTok and other platforms aren't supported** — only YouTube and
  Instagram, per the original scope decision.
- **No forced phoneme alignment or scene-detection frame scoring** —
  timestamps come from citation-matching against ASR/caption segments, and
  frames are a single `ffmpeg` grab per step, not the sharpest of a burst.
- **OCR under `launchd`/no GUI session is unverified** on the actual M1 Air
  target — Vision framework calls may behave differently without an active
  window-server session. Flagged in `deploy/README.md` as the first thing
  to check if OCR silently returns nothing once deployed.
