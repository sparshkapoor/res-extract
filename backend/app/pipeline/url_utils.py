import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models import Platform

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}

# Known tracking/referral params to strip. Anything not in this list (e.g.
# YouTube's essential `v=` on /watch URLs) is preserved.
_TRACKING_PARAMS = {"si", "feature", "pp", "ab_channel", "t", "igshid", "igsh", "utm_source",
                     "utm_medium", "utm_campaign", "fbclid"}


class UnsupportedUrlError(ValueError):
    pass


def detect_platform(url: str) -> Platform:
    host = urlsplit(url).hostname or ""
    host = host.lower()
    if host in _YOUTUBE_HOSTS:
        return Platform.youtube
    if host in _INSTAGRAM_HOSTS:
        return Platform.instagram
    raise UnsupportedUrlError(f"Unsupported host: {host!r}. Only YouTube and Instagram URLs are supported.")


def normalize_url(url: str) -> str:
    """Strip tracking params/fragments so the same video hashes identically
    regardless of how the URL was shared (e.g. `?si=...` on YouTube Shorts),
    while preserving essential params like YouTube's `?v=` on /watch URLs."""
    url = url.strip()
    parts = urlsplit(url)
    path = re.sub(r"/+$", "", parts.path) or "/"
    query_pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _TRACKING_PARAMS]
    query = urlencode(query_pairs)
    normalized = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))
    return normalized


def sha256_of_url(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()
