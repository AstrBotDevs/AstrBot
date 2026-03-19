from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.star import Star


class _DummyEvent:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply(self, message: str) -> None:
        self.replies.append(message)


@pytest.mark.asyncio
async def test_handle_error_fallback_does_not_instantiate_star(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_default_on_error(error: Exception, event, ctx) -> None:
        del ctx
        await event.reply(str(error))

    def _fail_init(self) -> None:
        raise AssertionError("Star should not be instantiated for fallback on_error")

    monkeypatch.setattr(Star, "default_on_error", staticmethod(_fake_default_on_error))
    monkeypatch.setattr(Star, "__init__", _fail_init)

    dispatcher = HandlerDispatcher(
        plugin_id="plugin", peer=SimpleNamespace(), handlers=[]
    )
    event = _DummyEvent()

    await dispatcher._handle_error(
        object(),
        RuntimeError("boom"),
        event,
        SimpleNamespace(),
    )

    assert event.replies == ["boom"]


@pytest.mark.asyncio
async def test_default_on_error_formats_astrbot_error_reply() -> None:
    event = _DummyEvent()
    error = AstrBotError.invalid_input(
        "bad payload",
        hint="check payload",
        docs_url="https://example.com/docs",
        details={"b": 2, "a": 1},
    )

    await Star.default_on_error(error, event, SimpleNamespace())

    assert len(event.replies) == 1
    assert "check payload" in event.replies[0]
    assert "https://example.com/docs" in event.replies[0]
    assert '"a": 1' in event.replies[0]
    assert '"b": 2' in event.replies[0]


@pytest.mark.asyncio
async def test_default_on_error_replies_generic_message_for_unknown_errors() -> None:
    event = _DummyEvent()

    await Star.default_on_error(RuntimeError("boom"), event, SimpleNamespace())

    assert len(event.replies) == 1
    assert event.replies[0]


@pytest.mark.asyncio
async def test_on_error_does_not_dispatch_via_subclass_default_on_error() -> None:
    class PluginWithShadowedDefault(Star):
        async def default_on_error(self, error: Exception, event, ctx) -> None:
            del error, event, ctx
            raise AssertionError(
                "Star.on_error should not virtual-dispatch default_on_error"
            )

    expected_event = _DummyEvent()
    actual_event = _DummyEvent()

    await Star.default_on_error(RuntimeError("boom"), expected_event, SimpleNamespace())
    await PluginWithShadowedDefault().on_error(
        RuntimeError("boom"),
        actual_event,
        SimpleNamespace(),
    )

    assert actual_event.replies == expected_event.replies
