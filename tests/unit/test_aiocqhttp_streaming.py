import asyncio
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@pytest.fixture
def streaming_event(monkeypatch):
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.send = AsyncMock()
    monkeypatch.setattr(AstrMessageEvent, "send_streaming", AsyncMock())
    monkeypatch.setattr(
        "astrbot.core.platform.astr_message_event.asyncio.sleep", AsyncMock()
    )
    return event


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        (["你好。世界！剩余"], ["你好。", "世界！", "剩余"]),
        (["……你好。余文"], ["你好。", "余文"]),
        (["……", "Hello. https://example.com"], ["……Hello. https://example.com"]),
        (["……", "你好", "。", "余文"], ["你好。", "余文"]),
        (["。。"], ["。。"]),
        (["、开头？！", "tail"], ["、开头？！", "tail"]),
        (["  甲。 \n乙？！", "尾 "], ["甲。", "乙？！", "尾"]),
        (
            ["English. URL:https://example.com/a?b=1"],
            ["English. URL:https://example.com/a?b=1"],
        ),
        (["a。" * 200 + "tail"], ["a。"] * 200 + ["tail"]),
        (["。", "a" * 1000, "b" * 1000], ["。" + "a" * 1000 + "b" * 1000]),
    ],
)
async def test_aiocqhttp_streaming_preserves_sentence_boundaries(
    streaming_event, chunks, expected
):
    async def stream():
        for text in chunks:
            yield MessageChain([Plain(text)])

    await streaming_event.send_streaming(stream(), use_fallback=True)

    assert [
        call.args[0].get_plain_text() for call in streaming_event.send.await_args_list
    ] == expected


@pytest.mark.asyncio
async def test_aiocqhttp_streaming_long_unterminated_tail_is_bounded(streaming_event):
    streaming_event.process_buffer = AsyncMock(
        side_effect=lambda buffer, pattern: buffer
    )

    async def stream():
        yield MessageChain([Plain("。tail")])

    await streaming_event.send_streaming(stream(), use_fallback=True)
    pattern = streaming_event.process_buffer.await_args.args[1]

    # A subprocess bounds the failure even when a synchronous regex blocks asyncio.
    # The old regex takes tens of seconds on this suffix; the anchored search is linear.
    await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-c",
            "import re, sys; "
            "assert re.compile(sys.argv[1]).search('。' + 'a' * 100_000) is None",
            pattern.pattern,
        ],
        check=True,
        capture_output=True,
        timeout=5,
    )
