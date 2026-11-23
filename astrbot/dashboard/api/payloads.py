"""Shared request decoding for the dashboard HTTP adapters."""

from typing import Any, Protocol

from starlette.requests import Request

from astrbot.core.utils.http_json import read_request_json


async def json_or_empty(request: Request) -> dict[str, Any]:
    """Decode an optional JSON object using the common request error policy."""
    data = await read_request_json(request, silent=True)
    return data if isinstance(data, dict) else {}


def required_text(value: object, name: str) -> str:
    """Normalize a required textual field without changing legacy coercion."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Missing key: {name}")
    return text


def model_dict(payload) -> dict[str, Any]:
    """Serialize an optional model or retain an existing dictionary."""
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    return payload if isinstance(payload, dict) else {}


class _RequestHeaders(Protocol):
    def get(self, key: str, default: str, /) -> str: ...


def request_locale(headers: _RequestHeaders, default: str = "zh-CN") -> str:
    """Select the first short language tag from a request header mapping."""
    raw_locale = headers.get("Accept-Language", "").strip()
    locale = raw_locale.split(",", 1)[0].split(";", 1)[0].strip()
    if not locale or len(locale) > 32:
        return default
    return locale
