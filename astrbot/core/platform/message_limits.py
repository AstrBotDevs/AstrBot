"""Platform hard-limit text splitting, distinct from UX segmented_reply."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

LimitUnit = Literal["chars", "bytes"]
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_SENTENCE_RE = re.compile(r"[.!?。！？](?:\s+|$)")
DEFAULT_MAX_CHUNKS = 20


class MessageLimitUnit(StrEnum):
    CHARS = "chars"
    BYTES = "bytes"


@dataclass(frozen=True, slots=True)
class PlatformTextLimit:
    """Hard send limit for one platform adapter."""

    max_length: int
    unit: MessageLimitUnit
    supports_markdown: bool
    supports_structured_components: bool
    allows_consecutive_messages: bool
    max_chunks: int = DEFAULT_MAX_CHUNKS


TELEGRAM_TEXT_LIMIT = PlatformTextLimit(
    max_length=4096,
    unit=MessageLimitUnit.CHARS,
    supports_markdown=True,
    supports_structured_components=True,
    allows_consecutive_messages=True,
)
DISCORD_TEXT_LIMIT = PlatformTextLimit(
    max_length=2000,
    unit=MessageLimitUnit.CHARS,
    supports_markdown=True,
    supports_structured_components=True,
    allows_consecutive_messages=True,
)
WECOM_TEXT_LIMIT = PlatformTextLimit(
    max_length=4096,
    unit=MessageLimitUnit.BYTES,
    supports_markdown=False,
    supports_structured_components=True,
    allows_consecutive_messages=True,
)


@dataclass(frozen=True, slots=True)
class TextChunks:
    """Split result plus whether the source was truncated after the cap."""

    parts: tuple[str, ...]
    truncated: bool


def _measure(text: str, unit: MessageLimitUnit) -> int:
    if unit is MessageLimitUnit.BYTES:
        return len(text.encode("utf-8"))
    return len(text)


def _slice_prefix(text: str, max_length: int, unit: MessageLimitUnit) -> str:
    if unit is MessageLimitUnit.CHARS:
        return text[:max_length]
    encoded = text.encode("utf-8")
    if len(encoded) <= max_length:
        return text
    return encoded[:max_length].decode("utf-8", errors="ignore")


def _active_fence(text: str) -> str | None:
    fence: str | None = None
    for line in text.splitlines():
        match = _FENCE_RE.match(line.strip())
        if not match:
            continue
        marker = match.group(1)
        if fence is None:
            fence = marker
        elif line.strip().startswith(fence[0] * len(fence)):
            fence = None
    return fence


def _close_and_reopen_fence(chunk: str, remainder: str) -> tuple[str, str]:
    fence = _active_fence(chunk)
    if fence is None:
        return chunk, remainder
    if not chunk.endswith("\n"):
        chunk += "\n"
    chunk += fence
    if remainder and not remainder.startswith("\n"):
        remainder = f"\n{remainder}"
    remainder = f"{fence}\n{remainder.lstrip(chr(10))}"
    return chunk, remainder


def _best_boundary(segment: str, unit: MessageLimitUnit) -> int | None:
    if not segment:
        return None
    candidates: list[int] = []

    fence_close = None
    fence: str | None = None
    offset = 0
    for line in segment.splitlines(keepends=True):
        stripped = line.strip()
        match = _FENCE_RE.match(stripped)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif stripped.startswith(fence[0] * len(fence)):
                fence_close = offset + len(line)
                fence = None
        offset += len(line)
    if fence_close:
        candidates.append(fence_close)

    table_break = None
    offset = 0
    previous_was_table = False
    for line in segment.splitlines(keepends=True):
        is_table = bool(_TABLE_ROW_RE.match(line))
        if previous_was_table and not is_table and offset > 0:
            table_break = offset
        previous_was_table = is_table
        offset += len(line)
    if table_break:
        candidates.append(table_break)

    paragraph = segment.rfind("\n\n")
    if paragraph > 0:
        candidates.append(paragraph + 2)
    newline = segment.rfind("\n")
    if newline > 0:
        candidates.append(newline + 1)
    sentence_matches = list(_SENTENCE_RE.finditer(segment))
    if sentence_matches:
        candidates.append(sentence_matches[-1].end())
    space = segment.rfind(" ")
    if space > 0:
        candidates.append(space + 1)

    usable = [index for index in candidates if 0 < index < len(segment)]
    if not usable:
        return None
    return max(usable)


def split_platform_text(
    text: str,
    limit: PlatformTextLimit,
) -> TextChunks:
    """Split text to satisfy a platform hard limit without UX segmented_reply.

    Args:
        text: Full message text.
        limit: Platform hard-limit descriptor.

    Returns:
        Ordered chunks and whether later content was dropped after max_chunks.
    """

    if not text:
        return TextChunks(parts=(), truncated=False)

    remaining = text
    parts: list[str] = []
    truncated = False
    while remaining:
        if _measure(remaining, limit.unit) <= limit.max_length:
            parts.append(remaining)
            break
        window = _slice_prefix(remaining, limit.max_length, limit.unit)
        if not window:
            truncated = True
            break
        boundary = _best_boundary(window, limit.unit)
        chunk = window[:boundary] if boundary else window
        remaining = remaining[len(chunk) :]
        chunk, remaining = _close_and_reopen_fence(chunk, remaining)
        if chunk:
            parts.append(chunk)
        if len(parts) >= limit.max_chunks:
            if remaining:
                truncated = True
            break
    return TextChunks(parts=tuple(parts), truncated=truncated)
