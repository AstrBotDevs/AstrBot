from __future__ import annotations

import re
from pathlib import Path

PLUGIN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9_])?$")
_WINDOWS_RESERVED_PLUGIN_IDS = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def validate_plugin_id(plugin_id: str) -> str:
    normalized = str(plugin_id).strip()
    if not normalized:
        raise ValueError("plugin_id must not be empty")
    if not PLUGIN_ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            "plugin_id must use only letters, digits, dots, underscores, or hyphens"
        )
    if normalized.upper() in _WINDOWS_RESERVED_PLUGIN_IDS:
        raise ValueError("plugin_id must not use a reserved Windows device name")
    return normalized


def resolve_plugin_data_dir(root: Path, plugin_id: str) -> Path:
    normalized = validate_plugin_id(plugin_id)
    resolved_root = root.resolve()
    candidate = (resolved_root / normalized).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("plugin_id escapes the plugin data root") from exc
    return candidate
