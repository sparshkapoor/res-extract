"""YouTube comment scraping + deterministic shortlisting (WS4d).

For fast-cut, no-narration, no-description short-form videos, quantity
information is sometimes unrecoverable from the video itself (see
evals/README.md's `sparse-short-1` case) but occasionally recoverable from
a viewer's own recreation posted in the comments. This module handles the
free, zero-model-call half of that pipeline stage: fetching comments and
filtering ~50 of them down to a couple of real candidates. The paid half
(judging whether a shortlisted comment actually describes this dish) is
`extract_recipe.rate_comment_confidence`.

YouTube only for v1 — yt-dlp's Instagram comment support is inconsistent
enough to defer; callers should gate on `platform == Platform.youtube`
themselves (see orchestrator.py) rather than this module silently no-oping
on Instagram URLs.
"""

import asyncio
import re
from dataclasses import dataclass

import yt_dlp

from app.pipeline.normalize import CANONICAL_UNIT_TOKENS, names_match


class CommentFetchError(RuntimeError):
    pass


@dataclass
class Comment:
    id: str
    text: str
    author: str
    like_count: int


_UNIT_TOKEN_SET = set(CANONICAL_UNIT_TOKENS)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _unit_token_density(text: str) -> int:
    """Counts occurrences of a canonical unit word (tsp, cup, clove, ...) in
    `text` — reuses normalize.py's unit table verbatim rather than a second
    hand-maintained list, so this and the normalizer can't drift apart on
    what counts as a unit."""
    tokens = _WORD_RE.findall(text.lower())
    return sum(1 for t in tokens if t in _UNIT_TOKEN_SET)


def _fetch_comments_sync(url: str, max_comments: int) -> list[Comment]:
    ydl_opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "getcomments": True,
        "extractor_args": {"youtube": {"comment_sort": ["top"], "max_comments": [str(max_comments)]}},
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise CommentFetchError(f"yt-dlp failed to fetch comments for {url}: {e}") from e

    raw_comments = info.get("comments") or []
    comments = [
        Comment(
            id=str(c.get("id", "")),
            text=(c.get("text") or "").strip(),
            author=c.get("author") or "",
            like_count=int(c.get("like_count") or 0),
        )
        for c in raw_comments
    ]
    return [c for c in comments if c.text][:max_comments]


async def fetch_top_comments(url: str, max_comments: int = 50) -> list[Comment]:
    """Best-effort — raises CommentFetchError on failure (comments disabled,
    rate limit, private video); callers should treat this as non-fatal, the
    same way vlm.VlmError is handled in orchestrator.py."""
    return await asyncio.to_thread(_fetch_comments_sync, url, max_comments)


def shortlist_recipe_like_comments(
    comments: list[Comment], extracted_ingredient_names: list[str], top_n: int = 2
) -> list[Comment]:
    """Deterministic, zero-model-call filter: scores each comment by how much
    it reads like an ingredient list for THIS dish — unit-token density
    (does it mention measurements at all?) plus how many of the recipe's own
    already-extracted ingredient names it mentions — and keeps only the top
    `top_n` comments with a nonzero score. Turns ~50 comments of banter into
    the 1-2 candidates worth spending an LLM confidence call on."""
    scored: list[tuple[int, Comment]] = []
    for comment in comments:
        density = _unit_token_density(comment.text)
        overlap = sum(1 for name in extracted_ingredient_names if names_match(name, comment.text))
        score = density + overlap
        if score > 0:
            scored.append((score, comment))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [comment for _score, comment in scored[:top_n]]
