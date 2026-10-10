"""Tests for the WakingCheckStage wake-prefix handling."""

from unittest.mock import MagicMock

import pytest

from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


class ConcreteAstrMessageEvent(AstrMessageEvent):
    """Concrete AstrMessageEvent for testing."""

    async def send(self, message):
        await super().send(message)


def _make_group_event(message_str: str) -> ConcreteAstrMessageEvent:
    """A group-chat event whose message chain has no components.

    A platform adapter can hand us a message that carries text but an empty
    component list (for example a forwarded/system payload), so get_messages()
    returns [].
    """
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.self_id = "bot123"
    message.session_id = "group123"
    message.message_id = "msg123"
    message.sender = MessageMember(user_id="user123", nickname="TestUser")
    message.message = []
    return ConcreteAstrMessageEvent(
        message_str=message_str,
        message_obj=message,
        platform_meta=PlatformMetadata(
            name="test_platform", description="", id="test_platform_id"
        ),
        session_id="group123",
    )


@pytest.fixture
def stage() -> WakingCheckStage:
    return WakingCheckStage()


async def _init(stage: WakingCheckStage, wake_prefix: list[str]) -> None:
    ctx = PipelineContext(
        astrbot_config={
            "platform_settings": {},
            "wake_prefix": wake_prefix,
            "admins_id": [],
        },
        plugin_manager=MagicMock(),
        astrbot_config_id="test",
    )
    await stage.initialize(ctx)


@pytest.mark.asyncio
async def test_empty_wake_prefix_with_empty_message_chain_wakes(stage):
    """An empty wake_prefix matches any text; an empty message chain must not
    crash the prefix check (it used to index messages[0] unconditionally)."""
    await _init(stage, wake_prefix=[""])
    event = _make_group_event("hello there")

    await stage.process(event)

    assert event.is_wake is True


@pytest.mark.asyncio
async def test_wake_prefix_with_empty_message_chain_wakes(stage):
    """Same edge case with a non-empty prefix: a matching text plus an empty
    chain should wake and strip the prefix rather than raising IndexError."""
    await _init(stage, wake_prefix=["/"])
    event = _make_group_event("/help")

    await stage.process(event)

    assert event.is_wake is True
    assert event.message_str == "help"
