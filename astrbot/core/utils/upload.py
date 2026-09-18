"""Shared streaming save for uploaded files.

Internal helper used by the dashboard/plugin upload wrappers so that every
upload endpoint writes request files to disk with bounded memory. Not part of
the plugin-facing API surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

COPY_BLOCK_SIZE = 1024 * 1024


class UploadTooLargeError(ValueError):
    """Raised when an upload exceeds the allowed size while saving."""

    def __init__(self, max_bytes: int) -> None:
        super().__init__(f"Uploaded file exceeds the {max_bytes} bytes limit")
        self.max_bytes = max_bytes


async def save_upload_stream(
    upload: Any,
    dest: str | Path,
    *,
    max_bytes: int | None = None,
) -> int:
    """Stream an uploaded file to disk in 1 MiB blocks.

    Args:
        upload: Upload object exposing async ``read(size)``; ``seek(0)`` is
            attempted best-effort before copying.
        dest: Destination file path.
        max_bytes: Optional hard limit. When the upload exceeds it, the
            partial file is removed and UploadTooLargeError is raised.

    Returns:
        Number of bytes written.

    Raises:
        UploadTooLargeError: The upload exceeded ``max_bytes``.
    """
    path = Path(dest)
    try:
        await upload.seek(0)
    except Exception:
        pass

    written = 0
    try:
        with path.open("wb") as output:
            while True:
                block = await upload.read(COPY_BLOCK_SIZE)
                if not block:
                    break
                written += len(block)
                if max_bytes is not None and written > max_bytes:
                    raise UploadTooLargeError(max_bytes)
                output.write(block)
    except BaseException:
        # Never leave a partial file behind on failure or cancellation.
        path.unlink(missing_ok=True)
        raise
    return written
