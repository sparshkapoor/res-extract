"""Bulk in-place repair of already-cached recipes using the deterministic
normalizer (app.pipeline.normalize) — no re-download, no models, safe to
run with Ollama/mlx down.

This is the bulk/offline equivalent of result_cache.get_cached()'s lazy
per-row self-heal: that path fixes one row the next time it's read; this
script fixes every row in one pass; both call the exact same
normalize_recipe() so they can never disagree.

It can only fix what's deterministically fixable (unit casing, misplaced
quantities, free-text-in-unit, name casing, dedupe — see normalize.py). It
cannot backfill a missing hero_image_path, null cook_time/servings, or a
title of "Unknown Recipe" — those need a real model pass; re-run
`scripts/smoke_test.py <url> --force` for that instead.

Usage:
    .venv/bin/python scripts/repair_cache.py                # dry-run, all rows
    .venv/bin/python scripts/repair_cache.py --apply         # write changes (backs up db first)
    .venv/bin/python scripts/repair_cache.py --url-hash H    # limit to one row
    .venv/bin/python scripts/repair_cache.py --apply --no-backup
"""

import argparse
import asyncio
import shutil
import sys
from datetime import UTC, datetime

from app.cache.result_cache import RECIPE_SCHEMA_VERSION
from app.config import get_settings
from app.db import get_db, init_db
from app.models import Recipe
from app.pipeline.normalize import normalize_recipe


def _diff_ingredients(before: Recipe, after: Recipe) -> list[str]:
    lines = []
    before_ings = before.ingredients
    after_ings = after.ingredients
    if len(before_ings) != len(after_ings):
        lines.append(f"    ingredient count: {len(before_ings)} -> {len(after_ings)} (dedupe)")
    for i, a in enumerate(after_ings):
        b = before_ings[i] if i < len(before_ings) else None
        if b is None:
            continue
        if (b.name, b.quantity, b.unit, getattr(b, "note", None)) != (a.name, a.quantity, a.unit, a.note):
            lines.append(
                f"    [{i}] name={b.name!r}->{a.name!r} qty={b.quantity!r}->{a.quantity!r} "
                f"unit={b.unit!r}->{a.unit!r} note={getattr(b, 'note', None)!r}->{a.note!r}"
            )
    return lines


async def main(apply: bool, url_hash_filter: str | None, backup: bool) -> None:
    await init_db()
    settings = get_settings()

    if apply and backup:
        backup_path = settings.db_path.with_name(
            f"{settings.db_path.name}.bak-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        )
        shutil.copy2(settings.db_path, backup_path)
        print(f"[repair_cache] backed up db to {backup_path}")

    query = "SELECT url_hash, url, recipe_json, schema_version FROM result_cache"
    params: tuple = ()
    if url_hash_filter:
        query += " WHERE url_hash = ?"
        params = (url_hash_filter,)

    async with get_db() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        if not rows:
            print("[repair_cache] no matching rows")
            return

        changed = 0
        for row in rows:
            before = Recipe.model_validate_json(row["recipe_json"])
            after = normalize_recipe(before)
            diff_lines = _diff_ingredients(before, after)
            is_changed = bool(diff_lines) or row["schema_version"] < RECIPE_SCHEMA_VERSION

            print(f"\n{row['url_hash'][:12]}  {before.title!r}  ({row['url']})")
            if not is_changed:
                print("    no changes")
                continue

            changed += 1
            for line in diff_lines:
                print(line)
            if row["schema_version"] < RECIPE_SCHEMA_VERSION:
                print(f"    schema_version: {row['schema_version']} -> {RECIPE_SCHEMA_VERSION}")

            if apply:
                await db.execute(
                    "UPDATE result_cache SET recipe_json = ?, schema_version = ? WHERE url_hash = ?",
                    (after.model_dump_json(), RECIPE_SCHEMA_VERSION, row["url_hash"]),
                )

        if apply:
            await db.commit()

        mode = "APPLIED" if apply else "DRY RUN"
        print(f"\n[repair_cache] {mode}: {changed}/{len(rows)} row(s) changed")
        if not apply and changed:
            print("[repair_cache] re-run with --apply to write these changes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write changes (default is dry-run)")
    parser.add_argument("--url-hash", default=None, help="limit repair to a single url_hash")
    parser.add_argument("--no-backup", action="store_true", help="skip the db.sqlite3 backup on --apply")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.apply, args.url_hash, backup=not args.no_backup))
    except KeyboardInterrupt:
        sys.exit(1)
