import contextlib
from collections.abc import AsyncIterator

import aiosqlite

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id              TEXT PRIMARY KEY,
    url                 TEXT NOT NULL,
    url_hash            TEXT NOT NULL,
    platform            TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'queued',
    stage_message       TEXT,
    error               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    result_cache_id     TEXT REFERENCES result_cache(url_hash)
);
CREATE INDEX IF NOT EXISTS idx_jobs_url_hash ON jobs(url_hash);

CREATE TABLE IF NOT EXISTS result_cache (
    url_hash        TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    recipe_json     TEXT NOT NULL,
    media_dir       TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS job_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL REFERENCES jobs(job_id),
    stage       TEXT NOT NULL,
    status      TEXT NOT NULL,
    message     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);
"""


async def init_db() -> None:
    settings = get_settings()
    async with aiosqlite.connect(settings.db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


@contextlib.asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    settings = get_settings()
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def sweep_orphaned_jobs() -> int:
    """On startup, mark any job left in a non-terminal state (from a prior
    crash/restart) as failed, so it doesn't hang forever in the DB."""
    terminal = ("done", "failed")
    async with get_db() as db:
        cursor = await db.execute(
            f"UPDATE jobs SET status = 'failed', error = 'server restarted mid-job', "
            f"updated_at = datetime('now') WHERE status NOT IN ({','.join('?' * len(terminal))})",
            terminal,
        )
        await db.commit()
        return cursor.rowcount
