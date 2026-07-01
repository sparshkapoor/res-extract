import pytest

from app.models import Platform
from app.pipeline.url_utils import UnsupportedUrlError, detect_platform, normalize_url, sha256_of_url


def test_detect_platform_youtube():
    assert detect_platform("https://www.youtube.com/watch?v=abc123") == Platform.youtube
    assert detect_platform("https://youtu.be/abc123") == Platform.youtube
    assert detect_platform("https://www.youtube.com/shorts/abc123") == Platform.youtube


def test_detect_platform_instagram():
    assert detect_platform("https://www.instagram.com/reel/abc123/") == Platform.instagram


def test_detect_platform_unsupported():
    with pytest.raises(UnsupportedUrlError):
        detect_platform("https://example.com/foo")
    with pytest.raises(UnsupportedUrlError):
        detect_platform("https://www.tiktok.com/@user/video/123")


def test_normalize_url_preserves_essential_query_param():
    # Regression test: normalize_url once stripped the ENTIRE query string,
    # which silently broke youtube.com/watch?v=... URLs (the `v` param is
    # not tracking noise — it's the video ID itself).
    url = "https://www.youtube.com/watch?v=qFsd8xDqCv8"
    assert normalize_url(url) == url


def test_normalize_url_strips_tracking_params_only():
    tracked = "https://www.youtube.com/watch?v=qFsd8xDqCv8&si=abc123"
    plain = "https://www.youtube.com/watch?v=qFsd8xDqCv8"
    assert normalize_url(tracked) == normalize_url(plain)
    assert "si=" not in normalize_url(tracked)
    assert "v=qFsd8xDqCv8" in normalize_url(tracked)


def test_normalize_url_strips_trailing_slash_and_lowercases_host():
    assert normalize_url("HTTPS://WWW.YOUTUBE.COM/shorts/abc123/") == "https://www.youtube.com/shorts/abc123"


def test_sha256_of_url_stable_across_tracking_variants():
    a = sha256_of_url("https://www.youtube.com/watch?v=qFsd8xDqCv8")
    b = sha256_of_url("https://www.youtube.com/watch?v=qFsd8xDqCv8&si=someTrackingJunk")
    assert a == b


def test_sha256_of_url_differs_for_different_videos():
    a = sha256_of_url("https://www.youtube.com/watch?v=aaaaaaaaaaa")
    b = sha256_of_url("https://www.youtube.com/watch?v=bbbbbbbbbbb")
    assert a != b
