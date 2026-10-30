import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import botpy.errors
import botpy.message
import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import (
    QQOfficialWebhookPlatformAdapter,
)


@pytest.fixture(params=[QQOfficialPlatformAdapter, QQOfficialWebhookPlatformAdapter])
def adapter_class(request):
    return request.param


def _make_adapter(adapter_class, default):
    config = {
        "id": "qq-test",
        "appid": "123",
        "secret": "test-secret",
        "enable_group_c2c": True,
        "enable_guild_direct_message": True,
    }
    if default is not None:
        config["use_markdown"] = default
    adapter = adapter_class(config, {}, asyncio.Queue())
    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "sent"}),
        post_message=AsyncMock(return_value={"id": "sent"}),
        post_dms=AsyncMock(return_value={"id": "sent"}),
    )
    return adapter


def _make_event(adapter, scene):
    raw_class = {
        "group": botpy.message.GroupMessage,
        "c2c": botpy.message.C2CMessage,
        "channel": botpy.message.Message,
        "direct": botpy.message.DirectMessage,
    }[scene]
    raw = raw_class(
        api=None,
        event_id="event-1",
        data={
            "id": "msg-1",
            "author": {
                "id": "user-1",
                "member_openid": "user-1",
                "user_openid": "user-1",
            },
            "group_openid": "group-1",
            "channel_id": "channel-1",
            "guild_id": "guild-1",
            "content": "ping",
            "timestamp": "0",
        },
    )
    message = AstrBotMessage()
    message.message_id = "msg-1"
    message.session_id = "session-1"
    message.self_id = "bot-1"
    message.sender = MessageMember(user_id="user-1", nickname="User")
    message.type = (
        MessageType.GROUP_MESSAGE
        if scene in ("group", "channel")
        else MessageType.FRIEND_MESSAGE
    )
    message.message_str = "ping"
    message.message = []
    message.raw_message = raw
    event = adapter.create_event(message)
    event.post_c2c_message = AsyncMock(return_value={"id": "sent"})
    return event


def _send_mock(event, scene):
    return {
        "group": event.bot.api.post_group_message,
        "c2c": event.post_c2c_message,
        "channel": event.bot.api.post_message,
        "direct": event.bot.api.post_dms,
    }[scene]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "default", [None, True, False], ids=["missing", "markdown", "plain"]
)
@pytest.mark.parametrize("explicit", [None, True, False])
@pytest.mark.parametrize("scene", ["group", "c2c", "channel", "direct"])
async def test_reply_format_precedence(adapter_class, default, explicit, scene):
    event = _make_event(_make_adapter(adapter_class, default), scene)
    await event.send(MessageChain([Plain("reply")], use_markdown_=explicit))

    sending = _send_mock(event, scene)
    sending.assert_awaited_once()
    payload = sending.await_args.kwargs
    expected_md = (default is not False) if explicit is None else explicit
    if expected_md:
        assert payload["markdown"] == {"content": "reply"}
        assert "content" not in payload
    else:
        assert payload["content"] == "reply"
        assert "markdown" not in payload
    assert payload.get("msg_type") == (
        (2 if expected_md else 0) if scene in ("group", "c2c") else None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("default", [None, True, False])
@pytest.mark.parametrize("explicit", [None, True, False])
@pytest.mark.parametrize("scene", ["group", "c2c", "channel"])
async def test_proactive_format_precedence(
    adapter_class, default, explicit, scene, monkeypatch
):
    adapter = _make_adapter(adapter_class, default)
    c2c_send = AsyncMock(return_value={"id": "sent"})
    monkeypatch.setattr(QQOfficialMessageEvent, "post_c2c_message", c2c_send)
    adapter.remember_session_scene("target", scene)
    adapter.remember_session_message_id("target", "msg-1")
    await adapter.send_by_session(
        MessageSession(
            adapter.meta().id,
            MessageType.FRIEND_MESSAGE if scene == "c2c" else MessageType.GROUP_MESSAGE,
            "target",
        ),
        MessageChain([Plain("proactive")], use_markdown_=explicit),
    )

    sending = {
        "group": adapter.client.api.post_group_message,
        "c2c": c2c_send,
        "channel": adapter.client.api.post_message,
    }[scene]
    sending.assert_awaited_once()
    payload = sending.await_args.kwargs
    expected_md = (default is not False) if explicit is None else explicit
    if expected_md:
        assert payload["markdown"] == {"content": "proactive"}
        assert "content" not in payload
    else:
        assert payload["content"] == "proactive"
        assert "markdown" not in payload
    assert payload.get("msg_type") == (
        2 if expected_md and scene != "channel" else None
    )


@pytest.mark.asyncio
async def test_event_constructor_keeps_historical_default(adapter_class):
    original = _make_event(_make_adapter(adapter_class, False), "group")
    event = type(original)(
        "ping", original.message_obj, original.platform_meta, "session-1", original.bot
    )
    await event.send(MessageChain([Plain("reply")]))
    assert event.bot.api.post_group_message.await_args.kwargs["markdown"] == {
        "content": "reply"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [True, False])
async def test_format_comes_from_actual_chunk(adapter_class, explicit):
    event = _make_event(_make_adapter(adapter_class, not explicit), "group")
    event.send_buffer = MessageChain([Plain("outer")], use_markdown_=not explicit)
    await event._post_send_one(MessageChain([Plain("chunk")], use_markdown_=explicit))
    payload = event.bot.api.post_group_message.await_args.kwargs
    assert payload.get("markdown") == ({"content": "chunk"} if explicit else None)
    assert payload.get("content") == (None if explicit else "chunk")


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [None, True, False])
async def test_split_media_keeps_format(adapter_class, explicit, monkeypatch):
    event = _make_event(_make_adapter(adapter_class, False), "group")
    chunks = []

    async def capture(chunk, stream=None):
        chunks.append(chunk)

    monkeypatch.setattr(event, "_post_send_one", capture)
    await event.send(
        MessageChain(
            [
                Plain("text"),
                Image(file="https://example.com/a.png"),
                Image(file="https://example.com/b.png"),
            ],
            use_markdown_=explicit,
        )
    )
    assert len(chunks) == 2
    assert all(chunk.use_markdown_ is explicit for chunk in chunks)


@pytest.mark.asyncio
@pytest.mark.parametrize("default", [True, False])
@pytest.mark.parametrize("scene", ["group", "c2c"])
@pytest.mark.parametrize(
    "media_index", [1, 3, 4, 5], ids=["image", "voice", "video", "file"]
)
async def test_media_keeps_its_payload_type(
    adapter_class, default, scene, media_index, monkeypatch
):
    event = _make_event(_make_adapter(adapter_class, default), scene)
    parsed = ["caption", None, None, None, None, None, None]
    parsed[media_index] = "media-data"
    monkeypatch.setattr(
        QQOfficialMessageEvent,
        "_parse_to_qqofficial",
        AsyncMock(return_value=tuple(parsed)),
    )
    monkeypatch.setattr(
        event,
        "upload_group_and_c2c_image",
        AsyncMock(return_value={"file_info": "media"}),
    )
    monkeypatch.setattr(
        event,
        "upload_group_and_c2c_media",
        AsyncMock(return_value={"file_info": "media"}),
    )
    await event.send(MessageChain([Plain("caption")]))
    payload = _send_mock(event, scene).await_args.kwargs
    assert payload["msg_type"] == 7
    assert payload["media"] == {"file_info": "media"}
    assert payload["content"] == "caption"
    assert "markdown" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize("default", [True, False])
@pytest.mark.parametrize("explicit", [None, True, False])
async def test_c2c_stream_obeys_format(adapter_class, default, explicit):
    event = _make_event(_make_adapter(adapter_class, default), "c2c")

    async def generate():
        for text in ["hello", " world"]:
            yield MessageChain([Plain(text)], use_markdown_=explicit)

    await event.send_streaming(generate())
    calls = event.post_c2c_message.await_args_list
    assert calls
    expected_md = default if explicit is None else explicit
    if not expected_md:
        assert len(calls) == 1
        assert calls[0].kwargs["content"] == "hello world"
        assert calls[0].kwargs["msg_type"] == 0
        assert "stream" not in calls[0].kwargs
        assert "markdown" not in calls[0].kwargs
    else:
        assert all(call.kwargs["msg_type"] == 2 for call in calls)
        assert calls[-1].kwargs["stream"]["state"] == 10
        assert (
            "".join(call.kwargs["markdown"]["content"] for call in calls)
            == "hello world\n"
        )


@pytest.mark.asyncio
async def test_c2c_markdown_override_closes_with_empty_tail(adapter_class):
    event = _make_event(_make_adapter(adapter_class, False), "c2c")

    async def generate():
        yield MessageChain([Plain("reply")], use_markdown_=True)

    await event.send_streaming(generate())
    payloads = [call.kwargs for call in event.post_c2c_message.await_args_list]
    assert all(payload["msg_type"] == 2 for payload in payloads)
    assert payloads[-1]["stream"]["state"] == 10
    assert "".join(payload["markdown"]["content"] for payload in payloads) == "reply\n"


@pytest.mark.asyncio
async def test_plain_c2c_stream_flushes_before_tool_call(adapter_class):
    event = _make_event(_make_adapter(adapter_class, False), "c2c")

    async def generate():
        yield MessageChain([Plain("before")])
        yield MessageChain(type="break")
        yield MessageChain([Plain("after")])

    await event.send_streaming(generate())
    assert [
        call.kwargs["content"] for call in event.post_c2c_message.await_args_list
    ] == ["before", "after"]
    assert all(
        "stream" not in call.kwargs for call in event.post_c2c_message.await_args_list
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("first_md", [True, False])
async def test_c2c_stream_format_changes_finish_previous_segment(
    adapter_class, first_md
):
    event = _make_event(_make_adapter(adapter_class, True), "c2c")

    async def generate():
        yield MessageChain([Plain("first")], use_markdown_=first_md)
        yield MessageChain([Plain("second")], use_markdown_=not first_md)

    await event.send_streaming(generate())
    payloads = [call.kwargs for call in event.post_c2c_message.await_args_list]
    plain = [payload for payload in payloads if payload["msg_type"] == 0]
    markdown = [payload for payload in payloads if payload["msg_type"] == 2]
    assert len(plain) == 1
    assert plain[0]["content"] == ("second" if first_md else "first")
    assert "stream" not in plain[0]
    assert "".join(payload["markdown"]["content"] for payload in markdown) == (
        "first\n" if first_md else "second\n"
    )
    assert markdown[-1]["stream"]["state"] == 10


@pytest.mark.asyncio
async def test_markdown_rejection_still_falls_back_once():
    sending = AsyncMock(
        side_effect=[
            botpy.errors.ServerError("不允许发送原生 markdown"),
            {"id": "sent"},
        ]
    )
    payload = {"markdown": {"content": "reply"}, "msg_type": 2}
    await QQOfficialMessageEvent._send_with_markdown_fallback(sending, payload, "reply")
    assert sending.await_count == 2
    assert sending.await_args_list[1].args[0] == {"content": "reply", "msg_type": 0}
    assert "markdown" in payload


@pytest.mark.asyncio
async def test_failed_markdown_fallback_propagates_error():
    error = botpy.errors.ServerError("fallback failed")
    sending = AsyncMock(
        side_effect=[botpy.errors.ServerError("不允许发送原生 markdown"), error]
    )
    with pytest.raises(botpy.errors.ServerError, match="fallback failed"):
        await QQOfficialMessageEvent._send_with_markdown_fallback(
            sending, {"markdown": {"content": "reply"}, "msg_type": 2}, "reply"
        )
    assert sending.await_count == 2
