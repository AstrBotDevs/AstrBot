from __future__ import annotations

from types import SimpleNamespace

from astrbot_sdk.decorators import LimiterMeta
from astrbot_sdk.errors import ErrorCodes
from astrbot_sdk.runtime.limiter import (
    DEFAULT_COOLDOWN_MESSAGE,
    DEFAULT_RATE_LIMIT_MESSAGE,
    LimiterEngine,
)


def test_limiter_engine_scopes_rate_limit_per_session() -> None:
    engine = LimiterEngine(clock=lambda: 10.0)
    limiter = LimiterMeta(kind="rate_limit", limit=1, window=30.0, scope="session")
    session_a = SimpleNamespace(session_id="session-a")
    session_b = SimpleNamespace(session_id="session-b")

    first = engine.evaluate(
        plugin_id="plugin",
        handler_id="plugin.handler",
        limiter=limiter,
        event=session_a,
    )
    blocked = engine.evaluate(
        plugin_id="plugin",
        handler_id="plugin.handler",
        limiter=limiter,
        event=session_a,
    )
    other_session = engine.evaluate(
        plugin_id="plugin",
        handler_id="plugin.handler",
        limiter=limiter,
        event=session_b,
    )

    assert first.allowed is True
    assert blocked.allowed is False
    assert blocked.hint == DEFAULT_RATE_LIMIT_MESSAGE
    assert other_session.allowed is True


def test_limiter_engine_error_behavior_returns_cooldown_error_details() -> None:
    engine = LimiterEngine(clock=lambda: 20.0)
    limiter = LimiterMeta(
        kind="cooldown",
        limit=1,
        window=8.2,
        scope="user",
        behavior="error",
    )
    event = SimpleNamespace(platform_id="test", user_id="user-1")

    engine.evaluate(
        plugin_id="plugin",
        handler_id="plugin.handler",
        limiter=limiter,
        event=event,
    )
    blocked = engine.evaluate(
        plugin_id="plugin",
        handler_id="plugin.handler",
        limiter=limiter,
        event=event,
    )

    assert blocked.allowed is False
    assert blocked.error is not None
    assert blocked.error.code == ErrorCodes.COOLDOWN_ACTIVE
    assert blocked.error.details == {
        "scope": "user",
        "handler_id": "plugin.handler",
        "remaining_seconds": 8.2,
    }
    assert blocked.error.hint == DEFAULT_COOLDOWN_MESSAGE.format(remaining_seconds=9)


def test_limiter_engine_silent_behavior_returns_no_hint_or_error() -> None:
    engine = LimiterEngine(clock=lambda: 5.0)
    limiter = LimiterMeta(
        kind="rate_limit",
        limit=1,
        window=10.0,
        scope="global",
        behavior="silent",
        message="custom {remaining_seconds}",
    )
    event = SimpleNamespace()

    engine.evaluate(
        plugin_id="plugin",
        handler_id="plugin.handler",
        limiter=limiter,
        event=event,
    )
    blocked = engine.evaluate(
        plugin_id="plugin",
        handler_id="plugin.handler",
        limiter=limiter,
        event=event,
    )

    assert blocked.allowed is False
    assert blocked.hint is None
    assert blocked.error is None
