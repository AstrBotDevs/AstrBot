from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from astrbot.core.utils.media_utils import file_uri_to_path, is_file_uri

ALLOWED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".svg",
    ".heic",
}


def resolve_file_url_path(image_ref: str) -> str:
    if not is_file_uri(image_ref):
        return image_ref
    return file_uri_to_path(image_ref)


def _is_path_within_roots(path: str, roots: Sequence[str]) -> bool:
    try:
        candidate = Path(path).resolve(strict=False)
    except Exception:
        return False

    for root in roots:
        try:
            root_path = Path(root).resolve(strict=False)
            candidate.relative_to(root_path)
            return True
        except Exception:
            continue
    return False


def is_supported_image_ref(
    image_ref: str,
    *,
    allow_extensionless_existing_local_file: bool = False,
    extensionless_local_roots: Sequence[str] | None = None,
) -> bool:
    if not image_ref:
        return False

    lowered = image_ref.lower()
    if lowered.startswith(("http://", "https://", "base64://")):
        return True

    file_path = (
        resolve_file_url_path(image_ref) if is_file_uri(image_ref) else image_ref
    )
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ALLOWED_IMAGE_EXTENSIONS:
        return True
    if not allow_extensionless_existing_local_file:
        return False
    if not extensionless_local_roots:
        return False
    # Keep support for extension-less temp files returned by image converters.
    return (
        ext == ""
        and os.path.exists(file_path)
        and _is_path_within_roots(file_path, extensionless_local_roots)
    )
