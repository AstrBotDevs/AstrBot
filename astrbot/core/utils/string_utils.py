from __future__ import annotations

from collections.abc import Iterable
from typing import Any


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
