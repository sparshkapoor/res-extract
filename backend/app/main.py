import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import routes_result, routes_status, routes_submit
from app.config import get_settings
from app.db import init_db, sweep_orphaned_jobs
from app.pipeline import vlm

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="res-extract")

# Same-origin in production (nginx proxies /api and /media to this process),
# but permissive here too so `npm run dev`'s Vite server can hit the API
# directly during frontend development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_submit.router, prefix="/api")
app.include_router(routes_status.router, prefix="/api")
app.include_router(routes_result.router, prefix="/api")

_settings = get_settings()
app.mount("/media/jobs", StaticFiles(directory=str(_settings.frames_dir)), name="job_media")
app.mount("/media/cache", StaticFiles(directory=str(_settings.cache_dir)), name="cache_media")


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()
    swept = await sweep_orphaned_jobs()
    if swept:
        logging.getLogger(__name__).warning("swept %d orphaned job(s) from a prior restart", swept)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    # WS5: the VLM worker is now a long-lived subprocess (see vlm.py) —
    # clean it up on server shutdown rather than leaving it orphaned.
    await vlm.shutdown()


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
