from __future__ import annotations

import os
from urllib.parse import unquote, urlparse

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
    parsed = urlparse(image_ref)
    if parsed.scheme != "file":
        return image_ref

    path = unquote(parsed.path or "")
    netloc = unquote(parsed.netloc or "")

    # Keep support for file://<host>/path and file://<path> forms.
    if netloc and netloc.lower() != "localhost":
        path = f"//{netloc}{path}" if path else netloc
    elif not path and netloc:
        path = netloc

    if os.name == "nt" and len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]

    return path or image_ref


def is_supported_image_ref(
    image_ref: str,
    *,
    allow_extensionless_existing_local_file: bool = True,
) -> bool:
    if not image_ref:
        return False

    lowered = image_ref.lower()
    if lowered.startswith(("http://", "https://", "base64://")):
        return True

    file_path = (
        resolve_file_url_path(image_ref) if lowered.startswith("file://") else image_ref
    )
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ALLOWED_IMAGE_EXTENSIONS:
        return True
    if not allow_extensionless_existing_local_file:
        return False
    # Keep support for extension-less temp files returned by image converters.
    return ext == "" and os.path.exists(file_path)
