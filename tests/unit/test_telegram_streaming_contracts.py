"""Verify public Telegram streams across delivery, cleanup, and media boundaries."""

import asyncio
import wave
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from PIL import Image as PillowImage
from telegram import Chat, Message
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ExtBot
from telegram.request import HTTPXRequest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain, Record, Video
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.telegram import tg_event

pytestmark = pytest.mark.asyncio


@dataclass
class StreamTransport:
    client: ExtBot
    calls: dict[str, AsyncMock]


@pytest_asyncio.fixture
async def transport(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[StreamTransport]:
    """Use the installed SDK and replace its outbound methods only."""
    request = HTTPXRequest()
    client = ExtBot(
        "123456:offline-token", request=request, get_updates_request=request
    )
    calls = {
        name: AsyncMock(return_value=None)
        for name in (
            "send_chat_action",
            "send_message",
            "edit_message_text",
            "send_message_draft",
            "send_photo",
            "send_animation",
            "send_document",
            "send_video",
            "send_voice",
        )
    }

    async def send_message(*, text: str, **kwargs: object) -> Message:
        if not text.strip():
            raise BadRequest("Message text is empty")
        return Message(
            message_id=calls["send_message"].await_count,
            date=datetime(2026, 1, 1, tzinfo=UTC),
            chat=Chat(id=int(str(kwargs["chat_id"])), type="supergroup"),
            text=text,
        )

    calls["send_message"].side_effect = send_message
    for name, callback in calls.items():
        monkeypatch.setattr(ExtBot, name, callback)
    try:
        yield StreamTransport(client, calls)
    finally:
        await request.shutdown()


def make_event(
    transport: StreamTransport, private: bool = False
) -> tg_event.TelegramPlatformEvent:
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE if private else MessageType.GROUP_MESSAGE
    message.self_id = "123456"
    message.session_id = "1001" if private else "-100#42"
    message.group_id = "" if private else "-100#42"
    message.message_id = "73"
    message.sender = MessageMember("1001", "Tester")
    message.message = [Plain("question")]
    message.message_str = "question"
    return tg_event.TelegramPlatformEvent(
        message.message_str,
        message,
        PlatformMetadata("telegram", "Telegram test", "telegram-stream-test"),
        message.session_id,
        transport.client,
    )


@pytest.mark.parametrize(
    "error_type", [TimedOut, NetworkError, RuntimeError, asyncio.CancelledError]
)
@pytest.mark.parametrize("cleanup_type", [RuntimeError, asyncio.CancelledError])
@pytest.mark.parametrize("private", [False, True], ids=["group", "private"])
async def test_primary_error_survives_generator_cleanup_failure(
    transport: StreamTransport,
    private: bool,
    error_type: type[BaseException],
    cleanup_type: type[BaseException],
) -> None:
    primary = error_type("Delivery outcome is unknown")
    cleanup = cleanup_type("Source cleanup failed")
    transport.calls["send_message"].side_effect = primary
    closed = []

    async def chunks() -> AsyncGenerator[MessageChain, None]:
        try:
            yield MessageChain([Plain("answer")])
            yield MessageChain(type="break")
            pytest.fail("A failed delivery must not consume another source item")
        finally:
            closed.append(True)
            raise cleanup

    source = chunks()
    with pytest.raises(error_type) as caught:
        await make_event(transport, private).send_streaming(source)

    assert caught.value is primary
    assert closed == [True]
    assert source.ag_frame is None
    transport.calls["send_message"].assert_awaited_once()
    transport.calls["edit_message_text"].assert_not_awaited()


class ClosingStream:
    """Model an iterator whose resource cleanup can fail after exhaustion."""

    def __init__(
        self, source: AsyncGenerator[MessageChain, None], error: BaseException
    ) -> None:
        self.source = source
        self.error = error
        self.close_count = 0

    def __aiter__(self) -> "ClosingStream":
        return self

    async def __anext__(self) -> MessageChain:
        return await anext(self.source)

    async def aclose(self) -> None:
        self.close_count += 1
        await self.source.aclose()
        raise self.error


@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_cleanup_only_error_is_visible(
    transport: StreamTransport, error_type: type[BaseException]
) -> None:
    error = error_type("Cleanup failed after delivery")

    async def chunks() -> AsyncGenerator[MessageChain, None]:
        yield MessageChain([Plain("delivered")])

    source = ClosingStream(chunks(), error)
    with pytest.raises(error_type) as caught:
        await make_event(transport).send_streaming(source)

    assert caught.value is error
    assert source.close_count == 1
    assert source.source.ag_frame is None
    transport.calls["send_message"].assert_awaited_once()


def make_media(tmp_path: Path, kind: str) -> tuple[BaseMessageComponent, str]:
    component: BaseMessageComponent
    if kind in {"photo", "animation"}:
        path = tmp_path / ("image.png" if kind == "photo" else "image.gif")
        PillowImage.new("RGB", (2, 2), "white").save(path)
        component = Image.fromFileSystem(path)
    elif kind == "voice":
        path = tmp_path / "audio.wav"
        with wave.open(str(path), "wb") as audio:
            audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\x00\x00" * 8)
        component = Record.fromFileSystem(path)
    else:
        path = tmp_path / ("video.mp4" if kind == "video" else "document.txt")
        path.write_bytes(b"local media transport fixture")
        component = (
            Video.fromFileSystem(path)
            if kind == "video"
            else File(name=path.name, file=str(path))
        )
    return component, f"send_{kind}"


@pytest.mark.parametrize("kind", ["photo", "animation", "voice", "video", "document"])
@pytest.mark.parametrize("later_text", [False, True], ids=["media_only", "later_text"])
@pytest.mark.parametrize("private", [False, True], ids=["group", "private"])
async def test_media_chunks_do_not_send_empty_text_or_block_later_text(
    transport: StreamTransport,
    tmp_path: Path,
    kind: str,
    later_text: bool,
    private: bool,
) -> None:
    media, send_method = make_media(tmp_path, kind)

    async def chunks() -> AsyncGenerator[MessageChain, None]:
        yield MessageChain([media])
        yield MessageChain([Plain("")])
        yield MessageChain([])
        yield MessageChain([At(qq="1001")])
        if later_text:
            yield MessageChain([Plain("answer")])
        yield MessageChain([Plain("")])

    source = chunks()
    await make_event(transport, private).send_streaming(source)

    transport.calls[send_method].assert_awaited_once()
    assert [
        call.kwargs["text"] for call in transport.calls["send_message"].await_args_list
    ] == (["answer"] if later_text else [])
    transport.calls["edit_message_text"].assert_not_awaited()
    assert source.ag_frame is None
    for call in transport.calls[send_method].await_args_list:
        assert call.kwargs["chat_id"] == ("1001" if private else "-100")
        if not private:
            assert call.kwargs["message_thread_id"] == 42
            assert type(call.kwargs["message_thread_id"]) is int


async def test_unchanged_chunks_preserve_media_and_repeat_text_after_break(
    transport: StreamTransport, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media, send_method = make_media(tmp_path, "photo")
    clock = [100.0]

    async def chunks() -> AsyncGenerator[MessageChain, None]:
        yield MessageChain([Plain("same")])
        clock[0] += 1
        yield MessageChain([Plain("")])
        yield MessageChain([media])
        yield MessageChain(type="break")
        yield MessageChain([Plain("same")])

    with monkeypatch.context() as patch:
        patch.setattr(asyncio.get_running_loop(), "time", lambda: clock[0])
        await make_event(transport).send_streaming(chunks())

    assert [
        call.kwargs["text"] for call in transport.calls["send_message"].await_args_list
    ] == ["same", "same"]
    transport.calls[send_method].assert_awaited_once()
    transport.calls["edit_message_text"].assert_not_awaited()


@pytest.mark.parametrize("later_text", [False, True])
@pytest.mark.parametrize("prefix", ["", " \t"], ids=["empty", "space_only"])
@pytest.mark.parametrize("segment_break", [False, True], ids=["finish", "break"])
@pytest.mark.parametrize("private", [False, True], ids=["group", "private"])
async def test_whitespace_chunks_wait_for_visible_text(
    transport: StreamTransport,
    monkeypatch: pytest.MonkeyPatch,
    later_text: bool,
    prefix: str,
    segment_break: bool,
    private: bool,
) -> None:
    # Keep rendering independent of the blank-message delivery contract.
    monkeypatch.setattr(tg_event.telegramify_markdown, "markdownify", lambda text: text)

    async def chunks() -> AsyncGenerator[MessageChain, None]:
        yield MessageChain([Plain(prefix)])
        if segment_break:
            yield MessageChain(type="break")
        if later_text:
            yield MessageChain([Plain("answer")])

    source = chunks()
    await make_event(transport, private).send_streaming(source)

    expected_text = "answer" if segment_break else f"{prefix}answer"
    assert [
        call.kwargs["text"] for call in transport.calls["send_message"].await_args_list
    ] == ([expected_text] if later_text else [])
    for method in ("send_message", "send_message_draft", "edit_message_text"):
        assert all(
            call.kwargs["text"].strip()
            for call in transport.calls[method].await_args_list
        )
    if not later_text:
        transport.calls["send_message_draft"].assert_not_awaited()
    transport.calls["edit_message_text"].assert_not_awaited()
    assert source.ag_frame is None


@pytest.mark.parametrize("phase", ["throttled", "break", "final"])
@pytest.mark.parametrize(
    "error_type", [TimedOut, NetworkError, RuntimeError, asyncio.CancelledError]
)
async def test_edit_outcome_is_not_replayed(
    transport: StreamTransport,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    error_type: type[BaseException],
) -> None:
    error = error_type("Edit outcome is unknown")
    transport.calls["edit_message_text"].side_effect = error
    clock = [100.0]
    closed = []

    async def chunks() -> AsyncGenerator[MessageChain, None]:
        try:
            yield MessageChain([Plain("first")])
            if phase == "throttled":
                clock[0] += 1
            yield MessageChain([Plain(" second")])
            if phase == "break":
                yield MessageChain(type="break")
        finally:
            closed.append(True)

    with monkeypatch.context() as patch:
        patch.setattr(asyncio.get_running_loop(), "time", lambda: clock[0])
        with pytest.raises(error_type) as caught:
            await make_event(transport).send_streaming(chunks())

    assert caught.value is error
    assert closed == [True]
    transport.calls["send_message"].assert_awaited_once()
    transport.calls["edit_message_text"].assert_awaited_once()


@pytest.mark.parametrize("formatter_fails", [False, True])
@pytest.mark.parametrize("fallback_fails", [False, True])
async def test_final_edit_plaintext_fallback_requires_preflight_or_explicit_rejection(
    transport: StreamTransport,
    monkeypatch: pytest.MonkeyPatch,
    formatter_fails: bool,
    fallback_fails: bool,
) -> None:
    error = TimedOut("Plaintext edit outcome is unknown")

    def markdownify(text: str) -> str:
        if formatter_fails:
            raise ValueError("Formatter failed before HTTP")
        return "escaped"

    monkeypatch.setattr(tg_event.telegramify_markdown, "markdownify", markdownify)
    transport.calls["edit_message_text"].side_effect = (
        [] if formatter_fails else [BadRequest("Invalid Markdown")]
    ) + [error if fallback_fails else None]

    async def chunks() -> AsyncGenerator[MessageChain, None]:
        yield MessageChain([Plain("first")])
        yield MessageChain([Plain(" second")])

    with monkeypatch.context() as patch:
        patch.setattr(asyncio.get_running_loop(), "time", lambda: 100.0)
        if fallback_fails:
            with pytest.raises(TimedOut) as caught:
                await make_event(transport).send_streaming(chunks())
            assert caught.value is error
        else:
            await make_event(transport).send_streaming(chunks())

    calls = [
        call.kwargs for call in transport.calls["edit_message_text"].await_args_list
    ]
    assert len(calls) == (1 if formatter_fails else 2)
    assert calls[-1] == {"text": "first second", "chat_id": "-100", "message_id": 1}
    if not formatter_fails:
        assert calls[0]["text"] == "escaped"
        assert calls[0]["parse_mode"] == "MarkdownV2"


async def test_task_cancellation_survives_cleanup_failure(
    transport: StreamTransport,
) -> None:
    entered = asyncio.Event()
    closed = asyncio.Event()
    cancellations = []

    async def send_message(**kwargs: object) -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError as error:
            cancellations.append(error)
            raise

    async def chunks() -> AsyncGenerator[MessageChain, None]:
        try:
            yield MessageChain([Plain("answer")])
        finally:
            closed.set()
            raise RuntimeError("Source cleanup failed")

    transport.calls["send_message"].side_effect = send_message
    task = asyncio.create_task(make_event(transport).send_streaming(chunks()))
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel("Caller cancelled delivery")
    with pytest.raises(asyncio.CancelledError) as caught:
        await task

    assert caught.value is cancellations[0]
    assert task.cancelled()
    assert closed.is_set()
    transport.calls["send_message"].assert_awaited_once()
