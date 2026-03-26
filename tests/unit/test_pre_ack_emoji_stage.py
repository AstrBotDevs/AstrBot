"""Tests for PreAckEmoji — emoji config behavior."""

from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.pipeline.pre_ack_emoji.stage import PreAckEmoji
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


class ConcreteAstrMessageEvent(AstrMessageEvent):
    async def send(self, message):
        await super().send(message)


def _make_config(enable=True, emojis=None, auto_remove=True, platform="telegram"):
    return {
        "platform_specific": {
            platform: {
                "pre_ack_emoji": {
                    "enable": enable,
                    "emojis": emojis or [],
                    "auto_remove": auto_remove,
                }
            }
        }
    }


def _make_event(platform="telegram", is_at_or_wake=True):
    meta = PlatformMetadata(name=platform, description="", id=f"{platform}_id")
    msg = AstrBotMessage()
    msg.type = MessageType.FRIEND_MESSAGE
    msg.self_id = "bot1"
    msg.session_id = "sess1"
    msg.message_id = "msg1"
    msg.sender = MessageMember(user_id="u1", nickname="Alice")
    msg.message = [Plain(text="hello")]
    msg.message_str = "hello"
    msg.raw_message = None

    event = ConcreteAstrMessageEvent(
        message_str="hello",
        message_obj=msg,
        platform_meta=meta,
        session_id="sess1",
    )
    event.is_at_or_wake_command = is_at_or_wake
    event.react = AsyncMock(return_value="reaction-42")
    event.unreact = AsyncMock()
    return event


# ── 关闭功能 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disabled_does_not_react():
    """enable=False 时不应调用 react()。"""
    pre_ack = PreAckEmoji(_make_config(enable=False, emojis=["👍"]))
    event = _make_event()

    await pre_ack.try_react(event)

    event.react.assert_not_called()


# ── 开启功能 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enabled_with_emoji_calls_react():
    """enable=True 且有表情时应调用 react()。"""
    pre_ack = PreAckEmoji(_make_config(enable=True, emojis=["👍"]))
    event = _make_event()

    await pre_ack.try_react(event)

    event.react.assert_called_once_with("👍")


# ── 空表情列表 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_emojis_does_not_react():
    """emojis 为空列表时不应触发。"""
    pre_ack = PreAckEmoji(_make_config(enable=True, emojis=[]))
    event = _make_event()

    await pre_ack.try_react(event)

    event.react.assert_not_called()


# ── 表情一致性 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_react_emoji_from_config_list():
    """react() 的参数必须在配置的 emojis 列表中。"""
    emojis = ["❤️", "🔥", "👀"]
    pre_ack = PreAckEmoji(_make_config(enable=True, emojis=emojis))
    event = _make_event()

    await pre_ack.try_react(event)

    event.react.assert_called_once()
    actual_emoji = event.react.call_args[0][0]
    assert actual_emoji in emojis


# ── auto_remove 开启 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_remove_calls_unreact():
    """auto_remove=True 时，try_unreact 应调用 unreact(reaction_id)。"""
    pre_ack = PreAckEmoji(_make_config(enable=True, emojis=["👍"], auto_remove=True))
    event = _make_event()

    await pre_ack.try_react(event)
    await pre_ack.try_unreact(event)

    event.unreact.assert_called_once_with("reaction-42")


# ── auto_remove 关闭 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_remove_false_skips_unreact():
    """auto_remove=False 时不应调用 unreact()。"""
    pre_ack = PreAckEmoji(_make_config(enable=True, emojis=["👍"], auto_remove=False))
    event = _make_event()

    await pre_ack.try_react(event)
    await pre_ack.try_unreact(event)

    event.unreact.assert_not_called()


# ── 不支持的平台 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_platform_skips():
    """不在支持列表中的平台不应触发。"""
    pre_ack = PreAckEmoji(
        _make_config(enable=True, emojis=["👍"], platform="qq_official")
    )
    event = _make_event(platform="qq_official")

    await pre_ack.try_react(event)

    event.react.assert_not_called()


# ── 未唤醒时不触发 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_not_wake_command_skips():
    """is_at_or_wake_command=False 时不应触发。"""
    pre_ack = PreAckEmoji(_make_config(enable=True, emojis=["👍"]))
    event = _make_event(is_at_or_wake=False)

    await pre_ack.try_react(event)

    event.react.assert_not_called()


# ── 未 react 时 unreact 不触发 ────────────────────────────


@pytest.mark.asyncio
async def test_unreact_skipped_when_no_react():
    """如果 try_react 未执行（条件不满足），try_unreact 也不应调用。"""
    pre_ack = PreAckEmoji(_make_config(enable=False, emojis=["👍"]))
    event = _make_event()

    await pre_ack.try_react(event)
    await pre_ack.try_unreact(event)

    event.unreact.assert_not_called()
