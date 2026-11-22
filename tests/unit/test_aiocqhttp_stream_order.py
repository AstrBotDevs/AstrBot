import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@pytest.fixture
def event(monkeypatch):
    event = object.__new__(AiocqhttpMessageEvent)
    event.send = AsyncMock()
    monkeypatch.setattr(AstrMessageEvent, "send_streaming", AsyncMock())
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    return event


@pytest.mark.asyncio
async def test_fallback_flushes_text_before_tool_status(event):
    async def generator():
        yield MessageChain([Plain("先行文本")])
        yield MessageChain(type="break")
        await event.send(MessageChain([Plain("调用工具")]))
        yield MessageChain([Plain("后续文本")])

    await event.send_streaming(generator(), use_fallback=True)

    sent_text = [call.args[0].chain[0].text for call in event.send.await_args_list]
    assert sent_text == ["先行文本", "调用工具", "后续文本"]


@pytest.mark.asyncio
async def test_fallback_flushes_text_before_media(event):
    async def generator():
        yield MessageChain([Plain("说明文字")])
        yield MessageChain([Image(file="base64://c2FtcGxl")])

    await event.send_streaming(generator(), use_fallback=True)

    calls = event.send.await_args_list
    assert len(calls) == 2
    assert isinstance(calls[0].args[0].chain[0], Plain)
    assert calls[0].args[0].chain[0].text == "说明文字"
    assert isinstance(calls[1].args[0].chain[0], Image)
