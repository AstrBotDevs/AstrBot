"""Tests for QQ Official single-message length splitting.

QQ 官方 API 对单条消息文本有长度上限（约 4000 字符，超限返回错误码
40054007）。适配器在发送前按该限制切分，防止长文本被平台截断。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import botpy.message
import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)


def _extract_send_text(kwargs: dict) -> str:
    text = kwargs.get("content")
    if text:
        return str(text)
    md = kwargs.get("markdown")
    if isinstance(md, dict):
        return str(md.get("content") or "")
    if md is not None:
        return str(getattr(md, "content", None) or "")
    return ""


def _make_group_event() -> QQOfficialMessageEvent:
    raw = botpy.message.GroupMessage(
        api=None,
        event_id="event-1",
        data={
            "id": "msg-1",
            "author": {"member_openid": "member-1"},
            "group_openid": "group-1",
            "content": "ping",
            "timestamp": "0",
        },
    )
    abm = AstrBotMessage()
    abm.message_id = "msg-1"
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


def _make_c2c_event() -> QQOfficialMessageEvent:
    raw = botpy.message.C2CMessage(
        api=None,
        event_id="event-2",
        data={
            "id": "msg-c2c",
            "author": {"user_openid": "user-1"},
            "content": "ping",
            "timestamp": "0",
        },
    )
    abm = AstrBotMessage()
    abm.message_id = "msg-c2c"
    abm.session_id = "user-1"
    abm.self_id = "bot-1"
    abm.sender = MessageMember(user_id="user-1", nickname="u")
    abm.type = MessageType.FRIEND_MESSAGE
    abm.message_str = "ping"
    abm.message = []
    abm.raw_message = raw
    meta = PlatformMetadata(name="qq_official", description="t", id="qq_official")
    bot = SimpleNamespace(api=SimpleNamespace(post_group_message=AsyncMock()))
    return QQOfficialMessageEvent(
        message_str="ping",
        message_obj=abm,
        platform_meta=meta,
        session_id="user-1",
        bot=bot,  # type: ignore[arg-type]
    )


def test_split_message_respects_limit() -> None:
    long_text = "不稀罕。" * 1500
    chunks = QQOfficialMessageEvent._split_message(long_text)
    assert len(chunks) > 1
    assert all(len(c) <= QQOfficialMessageEvent.QQ_MAX_LENGTH for c in chunks)
    assert "".join(chunks) == long_text


def test_split_message_short_unchanged() -> None:
    text = "短消息"
    assert QQOfficialMessageEvent._split_message(text) == [text]


def test_split_message_chain_by_length_keeps_short_media_chain() -> None:
    chain = MessageChain(chain=[Plain("标题"), Image(file="x.png")])
    assert QQOfficialMessageEvent._split_message_chain_by_length([chain]) == [chain]


def test_split_message_chain_by_length_splits_media_caption() -> None:
    caption = "标题" + "长" * 5000
    chain = MessageChain(chain=[Plain(caption), Image(file="x.png")])
    result = QQOfficialMessageEvent._split_message_chain_by_length([chain])
    assert len(result) > 1
    # 媒体保留在首个分片，其余分片为纯文本
    assert isinstance(result[0].chain[0], Image)
    assert all(not isinstance(c, Image) for c in result[0].chain[1:]) and all(
        not any(isinstance(c, Image) for c in ch.chain) for ch in result[1:]
    )
    texts = ["".join(c.text for c in ch.chain if isinstance(c, Plain)) for ch in result]
    assert all(len(t) <= QQOfficialMessageEvent.QQ_MAX_LENGTH for t in texts)
    assert "".join(texts) == caption


def test_split_message_chain_by_length_splits_long_text() -> None:
    chain = MessageChain(chain=[Plain("不稀罕。" * 1500)])
    result = QQOfficialMessageEvent._split_message_chain_by_length([chain])
    assert len(result) > 1
    assert all(
        len(c.chain[0].text) <= QQOfficialMessageEvent.QQ_MAX_LENGTH for c in result
    )
    assert "".join(c.chain[0].text for c in result) == chain.chain[0].text


@pytest.mark.asyncio
async def test_post_send_splits_long_reply_into_multiple_messages() -> None:
    event = _make_group_event()
    captured: list[str] = []

    async def capture(**kwargs):
        captured.append(_extract_send_text(kwargs))
        return {"id": f"out-{len(captured)}"}

    event.bot.api.post_group_message = AsyncMock(side_effect=capture)

    long_text = "不稀罕。" * 1500
    await event.send(MessageChain(chain=[Plain(long_text)]))

    assert len(captured) > 1
    assert all(len(t) <= QQOfficialMessageEvent.QQ_MAX_LENGTH for t in captured)
    assert "".join(captured) == long_text


@pytest.mark.asyncio
async def test_post_send_c2c_stream_split_streams_only_last_chunk() -> None:
    event = _make_c2c_event()
    event.send_buffer = MessageChain(chain=[Plain("不稀罕。" * 1500)])
    sent: list[dict | None] = []

    async def fake_post_c2c_message(openid, **kwargs):
        sent.append(kwargs.get("stream"))
        return SimpleNamespace(id=f"c2c-{len(sent)}")

    event.post_c2c_message = AsyncMock(  # type: ignore[method-assign]
        side_effect=fake_post_c2c_message
    )

    stream_payload = {"state": 1, "id": "prev-1", "index": 3, "reset": False}
    await event._post_send(stream=stream_payload)

    # 一次流式 flush 超长被拆成多段时，只有最后一段携带 stream 载荷，
    # 保证 C2C 流会话 id 连续、最终 state=10 能正常结束；其余段非流式发送。
    assert len(sent) > 1
    assert all(s is None for s in sent[:-1])
    assert sent[-1] == stream_payload


@pytest.mark.asyncio
async def test_send_by_session_splits_long_proactive_text() -> None:
    adapter = QQOfficialPlatformAdapter(
        {
            "id": "qq-official-test",
            "appid": "123",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        asyncio.Queue(),
    )
    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "sent-1"}),
        post_message=AsyncMock(),
    )
    adapter._session_scene["group-1"] = "group"

    long_text = "不稀罕。" * 1500
    await adapter.send_by_session(
        MessageSession("qq_official", MessageType.GROUP_MESSAGE, "group-1"),
        MessageChain(chain=[Plain(long_text)]),
    )

    assert adapter.client.api.post_group_message.await_count > 1
    sent = [
        _extract_send_text(kwargs)
        for _, kwargs in adapter.client.api.post_group_message.await_args_list
    ]
    assert all(len(t) <= QQOfficialMessageEvent.QQ_MAX_LENGTH for t in sent)
    assert "".join(sent) == long_text
