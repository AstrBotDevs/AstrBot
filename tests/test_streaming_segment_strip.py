import re

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


class CollectingMessageEvent(AstrMessageEvent):
    def __init__(self) -> None:
        message_obj = AstrBotMessage()
        message_obj.type = MessageType.FRIEND_MESSAGE
        message_obj.session_id = "user-1"
        message_obj.message_id = "msg-1"
        message_obj.self_id = "bot-1"
        message_obj.sender = MessageMember(user_id="user-1", nickname="tester")
        message_obj.message = []
        message_obj.message_str = ""
        message_obj.raw_message = None
        platform_meta = PlatformMetadata(
            name="test",
            description="test",
            id="test",
        )
        super().__init__("", message_obj, platform_meta, "user-1")
        self.sent_messages: list[MessageChain] = []

    async def send(self, message: MessageChain) -> None:
        self.sent_messages.append(message)


class CollectingAiocqhttpMessageEvent(AiocqhttpMessageEvent):
    async def send(self, message: MessageChain) -> None:
        self.sent_messages.append(message)


@pytest.mark.asyncio
async def test_process_buffer_strips_segment_leading_blank_lines(monkeypatch):
    event = CollectingMessageEvent()
    pattern = re.compile(r"[^。？！~…]+[。？！~…]+")
    sleep_calls = []

    async def sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        "astrbot.core.platform.astr_message_event.asyncio.sleep",
        sleep,
    )

    buffer = await event.process_buffer("你好。\n\n我是Astrbot。", pattern)

    sent_texts = [message.chain[0].text for message in event.sent_messages]
    assert buffer == ""
    assert sent_texts == ["你好。", "我是Astrbot。"]
    assert all(not text.startswith("\n") for text in sent_texts)
    assert sleep_calls == [1.5, 1.5]


@pytest.mark.asyncio
async def test_process_buffer_skips_sleep_when_stripped_segment_is_empty(monkeypatch):
    event = CollectingMessageEvent()
    sleep_calls = []

    async def sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        "astrbot.core.platform.astr_message_event.asyncio.sleep",
        sleep,
    )

    buffer = await event.process_buffer("   tail", re.compile(r"\s+"))

    assert buffer == "tail"
    assert event.sent_messages == []
    assert sleep_calls == []


@pytest.mark.asyncio
async def test_aiocqhttp_streaming_fallback_strips_tail_buffer(monkeypatch):
    event = CollectingAiocqhttpMessageEvent(
        "",
        CollectingMessageEvent().message_obj,
        PlatformMetadata(name="aiocqhttp", description="test", id="aiocqhttp"),
        "user-1",
        bot=None,
    )
    event.sent_messages = []

    async def sleep(_: float) -> None:
        return None

    async def generator():
        yield MessageChain([Plain("你好。\n\n我是Astrbot")])

    monkeypatch.setattr(
        "astrbot.core.platform.astr_message_event.asyncio.sleep",
        sleep,
    )

    await event.send_streaming(generator(), use_fallback=True)

    sent_texts = [message.chain[0].text for message in event.sent_messages]
    assert sent_texts == ["你好。", "我是Astrbot"]
    assert all(not text.startswith("\n") for text in sent_texts)
