from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def normalize_optional_text(value: str | None) -> str | None:
    """去除首尾空白后返回文本；None、空串、纯空白串一律归一为 None。"""
    if value is None:
        return None
    stripped = value.strip()
    return None if len(stripped) == 0 else stripped


def normalize_and_dedupe_strings(items: Iterable[Any] | None) -> list[str]:
    if items is None:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized
