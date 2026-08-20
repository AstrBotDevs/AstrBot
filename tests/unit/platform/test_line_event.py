from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.sources.line.line_event import LineMessageEvent


def _build_event(
    *, group_id: str | None = None, reply_token: str = "reply-1"
) -> LineMessageEvent:
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE if group_id else MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(user_id="user-1", nickname="Sender")
    message.self_id = "bot-1"
    message.session_id = group_id or "user-1"
    message.message_id = "msg-1"
    message.message = [Plain("hello")]
    message.message_str = "hello"
    message.raw_message = {"replyToken": reply_token} if reply_token else {}
    if group_id:
        message.group_id = group_id

    line_api = SimpleNamespace(
        reply_message=AsyncMock(return_value=True),
        push_message=AsyncMock(return_value=True),
    )
    return LineMessageEvent(
        message_str=message.message_str,
        message_obj=message,
        platform_meta=PlatformMetadata(
            name="line",
            description="LINE",
            id="line-test",
            support_streaming_message=False,
        ),
        session_id=message.session_id,
        line_api=line_api,
    )


@pytest.mark.asyncio
async def test_line_send_replies_when_reply_token_available(monkeypatch):
    event = _build_event(group_id="group-1", reply_token="reply-token")

    monkeypatch.setattr(
        LineMessageEvent,
        "build_line_messages",
        AsyncMock(return_value=[{"type": "text", "text": "hello"}]),
    )

    with patch.object(AstrMessageEvent, "send", AsyncMock()) as parent_send:
        await event.send(MessageChain([Plain("hello")]))

    event.line_api.reply_message.assert_awaited_once_with(
        "reply-token",
        [{"type": "text", "text": "hello"}],
    )
    event.line_api.push_message.assert_not_awaited()
    parent_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_send_falls_back_to_push_when_reply_fails(monkeypatch):
    event = _build_event(group_id="group-1", reply_token="reply-token")
    event.line_api.reply_message = AsyncMock(return_value=False)

    monkeypatch.setattr(
        LineMessageEvent,
        "build_line_messages",
        AsyncMock(return_value=[{"type": "text", "text": "hello"}]),
    )

    with patch.object(AstrMessageEvent, "send", AsyncMock()) as parent_send:
        await event.send(MessageChain([Plain("hello")]))

    event.line_api.reply_message.assert_awaited_once()
    event.line_api.push_message.assert_awaited_once_with(
        "group-1",
        [{"type": "text", "text": "hello"}],
    )
    parent_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_send_skips_parent_send_when_no_message_objects(monkeypatch):
    event = _build_event(reply_token="")

    monkeypatch.setattr(
        LineMessageEvent,
        "build_line_messages",
        AsyncMock(return_value=[]),
    )

    with patch.object(AstrMessageEvent, "send", AsyncMock()) as parent_send:
        await event.send(MessageChain([Plain("   ")]))

    event.line_api.reply_message.assert_not_awaited()
    event.line_api.push_message.assert_not_awaited()
    parent_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_build_line_messages_drops_unsendable_segments_after_limit(
    monkeypatch,
):
    image = Image.fromURL("https://example.test/a.png")
    file = File(name="report.pdf", url="https://example.test/report.pdf")
    chain = MessageChain(
        [
            Plain("one"),
            Plain("two"),
            Plain("three"),
            Plain("four"),
            Plain("five"),
            image,
            file,
        ]
    )

    monkeypatch.setattr(
        LineMessageEvent,
        "_resolve_image_url",
        AsyncMock(return_value="https://example.test/a.png"),
    )
    monkeypatch.setattr(
        LineMessageEvent,
        "_resolve_file_url",
        AsyncMock(return_value="https://example.test/report.pdf"),
    )
    monkeypatch.setattr(
        LineMessageEvent,
        "_resolve_file_size",
        AsyncMock(return_value=12),
    )

    messages = await LineMessageEvent.build_line_messages(chain)

    assert len(messages) == 5
    assert [message["text"] for message in messages] == [
        "one",
        "two",
        "three",
        "four",
        "five",
    ]


@pytest.mark.asyncio
async def test_line_send_streaming_aggregates_plain_segments_once():
    event = _build_event()
    event.send = AsyncMock()

    async def generator():
        yield MessageChain([Plain("Hello ")])
        yield MessageChain([Plain("world")])

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value="stream-finished"),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator())

    assert result == "stream-finished"
    event.send.assert_awaited_once()
    sent_chain = event.send.await_args.args[0]
    assert len(sent_chain.chain) == 1
    assert isinstance(sent_chain.chain[0], Plain)
    assert sent_chain.chain[0].text == "Hello world"
    parent_send_streaming.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_send_streaming_non_fallback_ignores_empty_generator():
    event = _build_event()
    event.send = AsyncMock()

    async def generator():
        if False:
            yield MessageChain([Plain("never")])

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value="stream-empty"),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator())

    assert result is None
    event.send.assert_not_awaited()
    parent_send_streaming.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_send_streaming_fallback_flushes_sentences_and_media(monkeypatch):
    event = _build_event()
    event.send = AsyncMock()
    image = Image.fromURL("https://example.test/image.png")

    async def generator():
        yield MessageChain([Plain("First~Second")])
        yield MessageChain([Plain(" last~")])
        yield MessageChain([image])

    with (
        patch.object(
            AstrMessageEvent,
            "send_streaming",
            AsyncMock(return_value="fallback-finished"),
        ) as parent_send_streaming,
        patch(
            "astrbot.core.platform.sources.line.line_event.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        result = await event.send_streaming(generator(), use_fallback=True)

    assert result == "fallback-finished"
    assert event.send.await_count == 3
    assert event.send.await_args_list[0].args[0].chain[0].text == "First~"
    assert event.send.await_args_list[1].args[0].chain[0].text == "Second last~"
    assert event.send.await_args_list[2].args[0].chain == [image]
    parent_send_streaming.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_send_streaming_fallback_flushes_trailing_plain_text():
    event = _build_event()
    event.send = AsyncMock()

    async def generator():
        yield MessageChain([Plain("tail without punctuation")])

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value="fallback-finished"),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator(), use_fallback=True)

    assert result == "fallback-finished"
    event.send.assert_awaited_once()
    assert event.send.await_args.args[0].chain[0].text == "tail without punctuation"
    parent_send_streaming.assert_awaited_once()
