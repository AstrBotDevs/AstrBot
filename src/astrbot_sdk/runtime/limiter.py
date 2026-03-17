from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..decorators import LimiterMeta
from ..errors import AstrBotError

DEFAULT_RATE_LIMIT_MESSAGE = "操作过于频繁，请稍后再试。"
DEFAULT_COOLDOWN_MESSAGE = "冷却中，请在 {remaining_seconds}s 后重试。"


@dataclass(slots=True)
class LimiterDecision:
    allowed: bool
    error: AstrBotError | None = None
    hint: str | None = None


class LimiterEngine:
    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._windows: dict[str, deque[float]] = {}

    def evaluate(
        self,
        *,
        plugin_id: str,
        handler_id: str,
        limiter: LimiterMeta,
        event: Any,
    ) -> LimiterDecision:
        now = float(self._clock())
        key = self._make_key(
            plugin_id=plugin_id,
            handler_id=handler_id,
            scope=limiter.scope,
            event=event,
        )
        bucket = self._windows.setdefault(key, deque())
        threshold = now - limiter.window
        while bucket and bucket[0] <= threshold:
            bucket.popleft()

        if len(bucket) < limiter.limit:
            bucket.append(now)
            return LimiterDecision(allowed=True)

        remaining = 0.0
        if bucket:
            remaining = max(0.0, limiter.window - (now - bucket[0]))
        hint = self._hint_text(limiter, remaining)
        details = {
            "scope": limiter.scope,
            "handler_id": handler_id,
            "remaining_seconds": round(remaining, 3),
        }
        if limiter.behavior == "silent":
            return LimiterDecision(allowed=False)
        if limiter.behavior == "error":
            if limiter.kind == "cooldown":
                return LimiterDecision(
                    allowed=False,
                    error=AstrBotError.cooldown_active(hint=hint, details=details),
                )
            return LimiterDecision(
                allowed=False,
                error=AstrBotError.rate_limited(hint=hint, details=details),
            )
        return LimiterDecision(allowed=False, hint=hint)

    @staticmethod
    def _make_key(
        *,
        plugin_id: str,
        handler_id: str,
        scope: str,
        event: Any,
    ) -> str:
        prefix = f"{plugin_id}:{handler_id}"
        if scope == "global":
            return prefix
        if scope == "session":
            return f"{prefix}:{getattr(event, 'session_id', '')}"
        if scope == "user":
            return (
                f"{prefix}:{getattr(event, 'platform_id', '')}"
                f":{getattr(event, 'user_id', '')}"
            )
        if scope == "group":
            return (
                f"{prefix}:{getattr(event, 'platform_id', '')}"
                f":{getattr(event, 'group_id', '')}"
            )
        return prefix

    @staticmethod
    def _hint_text(limiter: LimiterMeta, remaining: float) -> str:
        if limiter.message:
            return limiter.message.format(
                remaining_seconds=max(1, int(remaining + 0.999))
            )
        if limiter.kind == "cooldown":
            return DEFAULT_COOLDOWN_MESSAGE.format(
                remaining_seconds=max(1, int(remaining + 0.999))
            )
        return DEFAULT_RATE_LIMIT_MESSAGE


__all__ = [
    "DEFAULT_COOLDOWN_MESSAGE",
    "DEFAULT_RATE_LIMIT_MESSAGE",
    "LimiterDecision",
    "LimiterEngine",
]
