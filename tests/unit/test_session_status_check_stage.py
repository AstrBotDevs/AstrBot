from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.pipeline.session_status_check.stage import (
    SESSION_DISABLED_PASSTHROUGH_HANDLERS,
    SessionStatusCheckStage,
    allows_disabled_session,
)
from astrbot.core.star.command_ids import BUILTIN_COMMANDS_MODULE


class FakeEvent:
    def __init__(
        self,
        *,
        umo: str = "napcat:GroupMessage:1",
        handlers=(),
        platform_id: str = "napcat",
    ) -> None:
        self.unified_msg_origin = umo
        self._handlers = handlers
        self._platform_id = platform_id
        self.stopped = False

    def get_extra(self, key: str, default=None):
        if key == "activated_handlers":
            return self._handlers
        return default

    def get_platform_id(self) -> str:
        return self._platform_id

    def stop_event(self) -> None:
        self.stopped = True


async def _make_stage(*, session_enabled: bool) -> SessionStatusCheckStage:
    preferences = SimpleNamespace(
        get_async=AsyncMock(return_value={"session_enabled": session_enabled}),
    )
    conv_mgr = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="conv-1"),
        new_conversation=AsyncMock(),
    )
    stage = SessionStatusCheckStage()
    await stage.initialize(
        SimpleNamespace(
            execution_context=SimpleNamespace(conversation_manager=conv_mgr),
            preferences=preferences,
        )
    )
    stage.conv_mgr = conv_mgr
    return stage


def test_passthrough_handlers_use_stable_builtin_module_names():
    assert SESSION_DISABLED_PASSTHROUGH_HANDLERS == {
        f"{BUILTIN_COMMANDS_MODULE}_bot_status",
        f"{BUILTIN_COMMANDS_MODULE}_bot_enable",
    }


def test_allows_disabled_session_only_for_bot_status_and_enable():
    enable = SimpleNamespace(
        handler_full_name=f"{BUILTIN_COMMANDS_MODULE}_bot_enable",
    )
    disable = SimpleNamespace(
        handler_full_name=f"{BUILTIN_COMMANDS_MODULE}_bot_disable",
    )
    assert allows_disabled_session(FakeEvent(handlers=[enable])) is True
    assert allows_disabled_session(FakeEvent(handlers=[disable])) is False
    assert allows_disabled_session(FakeEvent()) is False


@pytest.mark.asyncio
async def test_initialize_requires_preferences():
    stage = SessionStatusCheckStage()
    with pytest.raises(RuntimeError, match="shared preferences"):
        await stage.initialize(
            SimpleNamespace(
                execution_context=SimpleNamespace(conversation_manager=None),
                preferences=None,
            )
        )


@pytest.mark.asyncio
async def test_enabled_session_does_not_stop_event():
    stage = await _make_stage(session_enabled=True)
    event = FakeEvent()
    await stage.process(event)
    assert event.stopped is False
    stage.conv_mgr.new_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_session_stops_unrelated_events():
    stage = await _make_stage(session_enabled=False)
    event = FakeEvent()
    await stage.process(event)
    assert event.stopped is True
    stage.conv_mgr.new_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_session_allows_bot_enable():
    stage = await _make_stage(session_enabled=False)
    event = FakeEvent(
        handlers=[
            SimpleNamespace(
                handler_full_name=f"{BUILTIN_COMMANDS_MODULE}_bot_enable",
            )
        ]
    )
    await stage.process(event)
    assert event.stopped is False
    stage.conv_mgr.new_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_session_creates_missing_conversation():
    stage = await _make_stage(session_enabled=False)
    stage.conv_mgr.get_curr_conversation_id = AsyncMock(return_value=None)
    event = FakeEvent(umo="napcat:GroupMessage:9")
    await stage.process(event)
    assert event.stopped is True
    stage.conv_mgr.new_conversation.assert_awaited_once_with(
        "napcat:GroupMessage:9",
        platform_id="napcat",
    )
