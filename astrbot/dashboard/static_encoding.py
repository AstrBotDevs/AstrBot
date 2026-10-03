"""Gzip encoding for dashboard static files.

Only JS, CSS, and HTML are compressed, and only when the client accepts gzip.
Images, fonts, and event streams are not handled here. Cache-Control is left
to the caller.
"""

from __future__ import annotations

import gzip
from collections.abc import Mapping

# text/javascript is what the stdlib reports for .js on current CPython.
# application/javascript is kept for older mimetypes maps.
COMPRESSIBLE_MEDIA_TYPES = frozenset(
    {
        "text/html",
        "text/css",
        "text/javascript",
        "application/javascript",
        "application/x-javascript",
    }
)

# Gzip of a few hundred bytes is often larger than the original.
MIN_GZIP_BYTES = 1024


def accepts_gzip(header: str | None) -> bool:
    """Return whether Accept-Encoding explicitly allows gzip with q > 0."""
    if not header:
        return False
    for part in header.split(","):
        bits = [item.strip() for item in part.split(";") if item.strip()]
        if not bits or bits[0].lower() != "gzip":
            continue
        quality = 1.0
        for param in bits[1:]:
            if not param.lower().startswith("q="):
                continue
            try:
                quality = float(param[2:])
            except ValueError:
                quality = 0.0
        return quality > 0
    return False


def is_compressible_media_type(media_type: str | None) -> bool:
    """Return whether this Content-Type is JS, CSS, or HTML."""
    if not media_type:
        return False
    base = media_type.split(";", 1)[0].strip().lower()
    return base in COMPRESSIBLE_MEDIA_TYPES


def gzip_static_body(data: bytes) -> bytes | None:
    """Return a smaller gzip body, or None when compression should be skipped."""
    if len(data) < MIN_GZIP_BYTES:
        return None
    compressed = gzip.compress(data, compresslevel=6)
    if len(compressed) >= len(data):
        return None
    return compressed


def with_gzip_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Add gzip headers without changing Cache-Control."""
    merged = dict(headers)
    merged["Content-Encoding"] = "gzip"
    vary = merged.get("Vary", "")
    parts = [part.strip() for part in vary.split(",") if part.strip()]
    if not any(part.lower() == "accept-encoding" for part in parts):
        parts.append("Accept-Encoding")
    merged["Vary"] = ", ".join(parts)
    return merged
