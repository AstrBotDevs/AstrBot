"""Bounded OTel-compatible values and local trace context (without an SDK)."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from itertools import islice
from typing import Any

MAX_ATTRIBUTE_BYTES = 16 * 1024
MAX_BODY_BYTES = 16 * 1024


def bounded_text(value: str, limit: int = MAX_BODY_BYTES) -> str:
    """Bound text by UTF-8 bytes without splitting a character.

    Args:
        value: Original text.
        limit: Maximum encoded length.

    Returns:
        Original text or text ending in a truncation marker.
    """
    encoded = value[:limit].encode("utf-8")
    if len(value) <= limit and len(encoded) <= limit:
        return value
    return (
        encoded[: max(0, limit - 16)].decode("utf-8", errors="ignore") + " [truncated]"
    )


def bounded_attributes(fields: dict[str, Any]) -> dict[str, Any]:
    """Convert application fields to bounded OTel attribute values.

    Nested objects are represented as JSON strings, not non-standard attribute
    objects. A shared byte budget also bounds wide and deeply nested inputs.

    Args:
        fields: Application attributes with their final names.

    Returns:
        Primitive attributes with an optional truncation marker.
    """
    remaining = MAX_ATTRIBUTE_BYTES - 64
    truncated = False
    result = {}
    for key, value in fields.items():
        key = bounded_text(str(key), 128)
        if value is None:
            continue
        if (
            isinstance(value, (list, tuple))
            and len(value) <= 128
            and (not value or type(value[0]) in (str, bool, int, float))
            and all(type(item) is type(value[0]) for item in value)
        ):
            original = value
            value = [
                bounded_text(item, 256) if isinstance(item, str) else item
                for item in value
            ]
            truncated |= value != list(original)
        elif not isinstance(value, (str, bool, int, float)):
            # Bound containers before serialization, including nested values.
            def compact(item: Any, depth: int = 0) -> Any:
                """Bound nested values before serialization."""
                nonlocal truncated
                if isinstance(item, str):
                    text = bounded_text(item, 2048)
                    truncated |= text != item
                    return text
                if depth >= 3:
                    truncated = True
                    return bounded_text(str(type(item).__name__), 128)
                if isinstance(item, dict):
                    truncated |= len(item) > 16
                    return {
                        str(k)[:128]: compact(v, depth + 1)
                        for k, v in islice(item.items(), 16)
                    }
                if isinstance(item, (list, tuple)):
                    truncated |= len(item) > 16
                    return [compact(v, depth + 1) for v in item[:16]]
                return (
                    item
                    if isinstance(item, (bool, int, float)) or item is None
                    else bounded_text(str(item), 2048)
                )

            try:
                value = json.dumps(compact(value), ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError):
                truncated = True
                continue
        if isinstance(value, str):
            original = value
            value = bounded_text(value, min(4096, max(16, remaining - len(key) - 16)))
            truncated |= value != original
        try:
            cost = len(
                json.dumps({key: value}, ensure_ascii=False, allow_nan=False).encode()
            )
        except ValueError:
            continue
        if cost > remaining:
            result["astrbot.truncated"] = True
            break
        result[key] = value
        remaining -= cost
    if truncated:
        result["astrbot.truncated"] = True
    return result


@dataclass
class TraceContext:
    """Trace identifiers whose lifetime also applies to copied task contexts."""

    trace_id: str
    span_id: str
    active: bool = True


current_trace_context: ContextVar[TraceContext | None] = ContextVar(
    "astrbot_trace_context", default=None
)


@contextmanager
def bind_trace_context(trace_id: str, span_id: str) -> Iterator[TraceContext]:
    """Bind IDs and invalidate detached copies on exit.

    Args:
        trace_id: Lowercase 32-character trace ID.
        span_id: Lowercase 16-character span ID.

    Yields:
        The active context.
    """
    context = TraceContext(trace_id, span_id)
    token = current_trace_context.set(context)
    try:
        yield context
    finally:
        context.active = False
        current_trace_context.reset(token)
