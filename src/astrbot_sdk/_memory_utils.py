from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any


def is_ttl_memory_entry(value: Any) -> bool:
    """Return whether a stored memory payload uses the TTL wrapper shape."""

    return isinstance(value, dict) and "value" in value and "ttl_seconds" in value


def memory_value_for_search(stored: Any) -> dict[str, Any] | None:
    """Unwrap the search payload from a stored memory record when possible."""

    if not isinstance(stored, dict):
        return None
    if is_ttl_memory_entry(stored):
        value = stored.get("value")
        return value if isinstance(value, dict) else None
    return stored


def extract_memory_text(stored: Any) -> str:
    """Pick the canonical text that keyword/vector search should index."""

    value = memory_value_for_search(stored)
    if not isinstance(value, dict):
        return ""
    for field_name in ("embedding_text", "content", "summary", "title", "text"):
        item = value.get(field_name)
        if isinstance(item, str) and item.strip():
            return item.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def memory_expiration_from_ttl(ttl_seconds: Any) -> datetime | None:
    """Translate a TTL in seconds into an absolute UTC expiration timestamp."""

    try:
        ttl = int(ttl_seconds)
    except (TypeError, ValueError):
        return None
    if ttl < 1:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=ttl)


def memory_expiration_from_stored_payload(stored: Any) -> datetime | None:
    """Recover an absolute expiration timestamp from a stored TTL payload."""

    if not is_ttl_memory_entry(stored) or not isinstance(stored, dict):
        return None
    raw_expires_at = stored.get("expires_at")
    if isinstance(raw_expires_at, (int, float)):
        return datetime.fromtimestamp(float(raw_expires_at), tz=timezone.utc)
    if not isinstance(raw_expires_at, str):
        return None

    normalized = raw_expires_at.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        expires_at = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at.astimezone(timezone.utc)


def memory_keyword_score(query: str, key: str, text: str) -> float:
    """Score a keyword hit the same way across runtime and core bridge."""

    normalized_query = str(query).casefold()
    if not normalized_query:
        return 1.0
    normalized_key = str(key).casefold()
    normalized_text = str(text).casefold()
    if normalized_query in normalized_key:
        return 1.0
    if normalized_query in normalized_text:
        return 0.9
    return 0.0


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Compute cosine similarity defensively for embedding vectors."""

    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=False)) / (
        left_norm * right_norm
    )


def memory_index_entry(entry: Any, *, text: str) -> dict[str, Any]:
    """Normalize cached sidecar data into a stable memory index record."""

    if isinstance(entry, dict):
        return {
            "text": str(entry.get("text", text)),
            "embedding": (
                [float(item) for item in entry.get("embedding", [])]
                if isinstance(entry.get("embedding"), list)
                else None
            ),
            "provider_id": (
                str(entry.get("provider_id")).strip()
                if entry.get("provider_id") is not None
                else None
            ),
        }
    return {"text": text, "embedding": None, "provider_id": None}
