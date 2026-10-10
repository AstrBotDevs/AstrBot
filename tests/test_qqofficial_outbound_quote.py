"""出站引用回复测试：QQ 官方群聊/单聊发送 message_reference。

背景：QQ 官方 API 的 message_reference.message_id 对「非机器人发的消息」需从
消息事件的 message_scene.ext 数组的 msg_idx 字段获取，格式为 REFIDX_...；
它与 message.id（ROBOT1.0_...）不是同一个值。此前适配器从不填充该字段，
导致开启 reply_with_quote 后回复仍不显示引用气泡。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Reply
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    PatchedC2CMessage,
    PatchedGroupMessage,
)

REF_IDX = "REFIDX_abc123+/def456=="


def _make_group_event(msg_idx: str | None = REF_IDX) -> QQOfficialMessageEvent:
    data: dict = {
        "id": "ROBOT1.0_message-id",
        "author": {"member_openid": "member-1"},
        "group_openid": "group-1",
        "content": "ping",
        "timestamp": "0",
    }
    if msg_idx is not None:
        data["message_scene"] = {
            "source": "default",
            "ext": [f"msg_idx={msg_idx}", "auth_token=TOKEN"],
        }
    # 生产环境的事件对象由 PatchedGroupMessage 构造，其 __init__ 会挂上 raw_data。
    raw = PatchedGroupMessage(api=None, event_id="event-1", data=data)

    abm = AstrBotMessage()
    abm.message_id = "ROBOT1.0_message-id"
    abm.session_id = "group-1"
    abm.group_id = "group-1"
    abm.self_id = "bot-1"
    abm.sender = MessageMember(user_id="member-1", nickname="u")
    abm.type = MessageType.GROUP_MESSAGE
    abm.message_str = "ping"
    abm.message = []
    abm.raw_message = raw
    meta = PlatformMetadata(name="qq_official", description="t", id="qq_official")
    bot = SimpleNamespace(api=SimpleNamespace(post_group_message=AsyncMock()))
    return QQOfficialMessageEvent(
        message_str="ping",
        message_obj=abm,
        platform_meta=meta,
        session_id="group-1",
        bot=bot,  # type: ignore[arg-type]
    )


def _make_c2c_event(msg_idx: str | None = REF_IDX) -> QQOfficialMessageEvent:
    data: dict = {
        "id": "ROBOT1.0_c2c-id",
        "author": {"user_openid": "user-1"},
        "content": "ping",
        "timestamp": "0",
    }
    if msg_idx is not None:
        data["message_scene"] = {"source": "default", "ext": [f"msg_idx={msg_idx}"]}
    raw = PatchedC2CMessage(api=None, event_id="event-1", data=data)

    abm = AstrBotMessage()
    abm.message_id = "ROBOT1.0_c2c-id"
    abm.session_id = "user-1"
    abm.self_id = "bot-1"
    abm.sender = MessageMember(user_id="user-1", nickname="u")
    abm.type = MessageType.FRIEND_MESSAGE
    abm.message_str = "ping"
    abm.message = []
    abm.raw_message = raw
    meta = PlatformMetadata(name="qq_official", description="t", id="qq_official")
    bot = SimpleNamespace(
        api=SimpleNamespace(
            post_group_message=AsyncMock(),
            post_c2c_message=AsyncMock(return_value={"id": "out-1"}),
        )
    )
    return QQOfficialMessageEvent(
        message_str="ping",
        message_obj=abm,
        platform_meta=meta,
        session_id="user-1",
        bot=bot,  # type: ignore[arg-type]
    )


def test_extract_self_ref_idx_reads_msg_idx() -> None:
    event = _make_group_event()
    assert event._extract_self_ref_idx(event.message_obj.raw_message) == REF_IDX


def test_extract_self_ref_idx_returns_empty_without_message_scene() -> None:
    event = _make_group_event(msg_idx=None)
    assert event._extract_self_ref_idx(event.message_obj.raw_message) == ""


def test_extract_self_ref_idx_returns_empty_for_non_dict_raw_data() -> None:
    event = _make_group_event()
    assert event._extract_self_ref_idx(SimpleNamespace(raw_data="nope")) == ""


@pytest.mark.asyncio
async def test_group_send_fills_message_reference_when_reply_component_present() -> None:
    event = _make_group_event()
    event.bot.api.post_group_message = AsyncMock(return_value={"id": "out-1"})

    await event.send_streaming(_gen_with_reply())

    event.bot.api.post_group_message.assert_awaited()
    kwargs = event.bot.api.post_group_message.await_args.kwargs
    assert kwargs["message_reference"] == {"message_id": REF_IDX}
    assert kwargs["msg_id"] == "ROBOT1.0_message-id"


@pytest.mark.asyncio
async def test_group_send_omits_message_reference_without_reply_component() -> None:
    event = _make_group_event()
    event.bot.api.post_group_message = AsyncMock(return_value={"id": "out-1"})

    await event.send_streaming(_gen_without_reply())

    kwargs = event.bot.api.post_group_message.await_args.kwargs
    assert "message_reference" not in kwargs


@pytest.mark.asyncio
async def test_message_reference_omitted_when_msg_idx_missing() -> None:
    event = _make_group_event(msg_idx=None)
    event.bot.api.post_group_message = AsyncMock(return_value={"id": "out-1"})

    await event.send_streaming(_gen_with_reply())

    kwargs = event.bot.api.post_group_message.await_args.kwargs
    assert "message_reference" not in kwargs


async def _gen_with_reply():
    yield MessageChain(chain=[Reply(id="ROBOT1.0_message-id"), Plain("hi")])


async def _gen_without_reply():
    yield MessageChain(chain=[Plain("hi")])
