from __future__ import annotations

import os
from urllib.parse import urlsplit

from astrbot.core.utils.image_ref_utils import ALLOWED_IMAGE_EXTENSIONS

IMAGE_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS


def normalize_file_like_url(path: str | None) -> str | None:
    if path is None:
        return None
    if not isinstance(path, str):
        return None
    if "?" not in path and "#" not in path:
        return path
    try:
        split = urlsplit(path)
    except Exception:
        return path
    return split.path or path


def looks_like_image_file_name(name: str) -> bool:
    normalized_name = normalize_file_like_url(name)
    if not isinstance(normalized_name, str) or not normalized_name.strip():
        return False
    _, ext = os.path.splitext(normalized_name.strip().lower())
    return ext in IMAGE_EXTENSIONS


def convert_data_image_to_base64_ref(image_ref: str) -> str | None:
    if not isinstance(image_ref, str):
        return None
    value = image_ref.strip()
    if not value:
        return None
    lower_value = value.lower()
    if not lower_value.startswith("data:image/"):
        return None

    comma_index = value.find(",")
    if comma_index <= 0:
        return None
    header = value[:comma_index].lower()
    payload = value[comma_index + 1 :].strip()
    if ";base64" not in header or not payload:
        return None
    return f"base64://{payload}"


def get_existing_local_path(value: str) -> str | None:
    lower_value = value.lower()
    if lower_value.startswith("file://"):
        file_path = value[7:]
        if file_path.startswith("/") and len(file_path) > 3 and file_path[2] == ":":
            file_path = file_path[1:]
        if file_path and os.path.exists(file_path):
            return os.path.abspath(file_path)
        return None
    if os.path.exists(value):
        return os.path.abspath(value)
    return None


def normalize_image_ref(image_ref: str) -> str | None:
    if not isinstance(image_ref, str):
        return None
    value = image_ref.strip()
    if not value:
        return None
    lower_value = value.lower()

    if lower_value.startswith(("http://", "https://")):
        return value
    if lower_value.startswith("base64://"):
        return value

    data_image_ref = convert_data_image_to_base64_ref(value)
    if data_image_ref:
        return data_image_ref

    local_path = get_existing_local_path(value)
    if local_path and looks_like_image_file_name(local_path):
        return local_path
    return None
