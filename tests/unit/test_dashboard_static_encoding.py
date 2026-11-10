"""Tests for dashboard static gzip encoding."""

import gzip

from astrbot.dashboard.static_encoding import (
    accepts_gzip,
    gzip_static_body,
    is_compressible_media_type,
    with_gzip_headers,
)


def test_accepts_gzip_only_when_explicitly_allowed():
    assert accepts_gzip("gzip")
    assert accepts_gzip("br, gzip, deflate")
    assert accepts_gzip("gzip;q=0.8")
    assert not accepts_gzip(None)
    assert not accepts_gzip("")
    assert not accepts_gzip("br")
    assert not accepts_gzip("gzip;q=0")
    assert not accepts_gzip("identity")


def test_only_js_css_and_html_are_compressible():
    assert is_compressible_media_type("text/javascript")
    assert is_compressible_media_type("text/javascript; charset=utf-8")
    assert is_compressible_media_type("application/javascript")
    assert is_compressible_media_type("text/css")
    assert is_compressible_media_type("text/html")
    assert not is_compressible_media_type("font/woff2")
    assert not is_compressible_media_type("image/png")
    assert not is_compressible_media_type("image/svg+xml")
    assert not is_compressible_media_type("text/event-stream")
    assert not is_compressible_media_type("application/json")
    assert not is_compressible_media_type(None)


def test_gzip_static_body_shrinks_text_and_skips_tiny_payloads():
    raw = b"function boot(){return 'dashboard';}" * 80
    compressed = gzip_static_body(raw)
    assert compressed is not None
    assert len(compressed) < len(raw)
    assert gzip.decompress(compressed) == raw
    assert gzip_static_body(b"tiny") is None


def test_gzip_headers_keep_cache_control():
    headers = with_gzip_headers({"Cache-Control": "no-cache", "Vary": "Origin"})
    assert headers["Cache-Control"] == "no-cache"
    assert headers["Content-Encoding"] == "gzip"
    assert headers["Vary"] == "Origin, Accept-Encoding"
