"""Read and normalize the Codex account's usage without changing OAuth state."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import math
import time
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
_CACHE_SECONDS = 60


def _number(
    value: Any, *, minimum: float = 0, maximum: float | None = None
) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return None
    if (
        not math.isfinite(result)
        or result < minimum
        or (maximum is not None and result > maximum)
    ):
        return None
    return result


def _integer(value: Any) -> int | None:
    result = _number(value)
    if result is None or not result.is_integer():
        return None
    return int(result)


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _label(value: Any, *, max_length: int = 64) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > max_length or any(ord(char) < 32 for char in text):
        return None
    return text


def _balance(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return str(value)


def _window(
    bucket: str, limit_id: str | None, name: str | None, payload: Any
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    used = _number(payload.get("used_percent"), maximum=100)
    return {
        "bucket": bucket,
        "limit_id": limit_id,
        "name": name,
        "used_percent": used,
        "remaining_percent": 100 - used if used is not None else None,
        "window_seconds": _integer(payload.get("limit_window_seconds")),
        "reset_at": _integer(payload.get("reset_at")),
    }


def _normalize(payload: dict[str, Any], observed_at: str) -> dict[str, Any]:
    windows: list[dict[str, Any]] = []
    main_limit = payload.get("rate_limit")
    if not isinstance(main_limit, dict):
        main_limit = {}

    def append_windows(
        limit: dict[str, Any], limit_id: str | None, name: str | None
    ) -> None:
        for bucket in ("primary", "secondary"):
            item = _window(bucket, limit_id, name, limit.get(f"{bucket}_window"))
            if item is not None:
                windows.append(item)

    append_windows(main_limit, "codex", None)
    additional = payload.get("additional_rate_limits")
    if isinstance(additional, list):
        for entry in additional:
            if isinstance(entry, dict) and isinstance(entry.get("rate_limit"), dict):
                append_windows(
                    entry["rate_limit"],
                    _label(entry.get("metered_feature"))
                    or _label(entry.get("limit_id")),
                    _label(entry.get("limit_name")),
                )

    credits = payload.get("credits")
    if not isinstance(credits, dict):
        credits = {}
    return {
        "status": "success",
        "observed_at": observed_at,
        "cached": False,
        "plan_type": _label(payload.get("plan_type"), max_length=32),
        "windows": windows,
        "limit_reached": _boolean(main_limit.get("limit_reached")),
        "credits": {
            "has_credits": _boolean(credits.get("has_credits")),
            "unlimited": _boolean(credits.get("unlimited")),
            "balance": _balance(credits.get("balance")),
        },
    }


class QuotaReader:
    """Fetches the fixed ChatGPT usage endpoint through a Codex OAuth provider."""

    def __init__(
        self,
        *,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client_factory = client_factory
        self._clock = clock
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._closed = False

    @staticmethod
    def _identity(provider: Any) -> tuple[dict[str, str], str] | None:
        try:
            headers = provider._build_backend_headers()
        except Exception:
            return None
        if not isinstance(headers, dict):
            return None
        safe_headers = {str(key): str(value) for key, value in headers.items()}
        lower = {key.lower(): value for key, value in safe_headers.items()}
        authorization = lower.get("authorization", "").strip()
        account = lower.get("chatgpt-account-id", "").strip()
        if (
            not authorization.startswith("Bearer ")
            or not authorization[7:].strip()
            or not account
        ):
            return None
        fingerprint = hashlib.sha256(f"{authorization}\0{account}".encode()).hexdigest()
        safe_headers = {
            key: value for key, value in safe_headers.items() if key.lower() != "accept"
        }
        safe_headers["Accept"] = "application/json"
        return safe_headers, fingerprint

    async def read(self, provider: Any) -> dict[str, Any]:
        if self._closed:
            return {"status": "closed"}
        if str(getattr(provider, "base_url", "")).rstrip("/") != _CODEX_BASE_URL:
            return {"status": "unsupported_endpoint"}

        async with self._lock:
            if self._closed:
                return {"status": "closed"}
            for _ in range(3):
                identity = self._identity(provider)
                if identity is None:
                    return {"status": "unbound"}
                headers, fingerprint = identity
                now = self._clock()
                cached = self._cache.get(fingerprint)
                if cached is not None and 0 <= now - cached[0] < _CACHE_SECONDS:
                    result = copy.deepcopy(cached[1])
                    result["cached"] = True
                    return result

                config = getattr(provider, "provider_config", None)
                proxy = config.get("proxy") if isinstance(config, dict) else None
                try:
                    async with self._client_factory(
                        proxy=proxy or None,
                        timeout=15.0,
                        trust_env=False,
                        follow_redirects=False,
                    ) as client:
                        response = await client.get(_USAGE_URL, headers=headers)
                except Exception:
                    if self._closed:
                        return {"status": "closed"}
                    return {"status": "unavailable"}

                if self._closed:
                    return {"status": "closed"}
                current = self._identity(provider)
                if current is None:
                    return {"status": "unbound"}
                if current[1] != fingerprint:
                    continue

                status = response.status_code
                if status != 200:
                    category = {
                        401: "reauth_required",
                        403: "forbidden",
                        429: "rate_limited",
                    }.get(status, "unavailable")
                    return {"status": category, "http_status": status}
                try:
                    payload = response.json()
                except ValueError:
                    return {"status": "unparseable"}
                if not isinstance(payload, dict):
                    return {"status": "unparseable"}

                observed_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
                result = _normalize(payload, observed_at)
                self._cache = {fingerprint: (now, result)}
                return copy.deepcopy(result)
            return {"status": "unavailable"}

    async def close(self) -> None:
        self._closed = True
        async with self._lock:
            self._cache.clear()
