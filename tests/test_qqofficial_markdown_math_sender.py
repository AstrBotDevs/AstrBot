import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import botpy.errors
import botpy.message
import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import AstrBotMessage, MessageMember, PlatformMetadata
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.qqofficial.qq_markdown_math import (
    normalize_qq_list_math,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)

SOURCE = "1. Formula:\n   $$x + y = z$$\n"


@pytest.fixture(autouse=True)
def disable_metrics_storage(monkeypatch):
    from astrbot.core.utils.metrics import Metric

    monkeypatch.setattr(Metric, "upload", AsyncMock())


class Transport:
    def __init__(self):
        self.frames = []
        self.cards = {}
        self.api = SimpleNamespace(_http=self, post_group_message=self.group_send)

    def accept(self, payload):
        frame = copy.deepcopy(payload)
        self.frames.append(frame)
        assert "state" not in frame
        stream = frame.get("stream") or {}
        card_id = stream.get("id") or f"card-{len(self.cards) + 1}"
        text = (
            (frame.get("markdown") or {}).get("content") or frame.get("content") or ""
        )
        if stream.get("reset"):
            assert stream["index"] == 1
            self.cards[card_id] = text
        else:
            self.cards[card_id] = self.cards.get(card_id, "") + text
        return {"id": card_id}

    async def request(self, route, json):
        return self.accept(json)

    async def group_send(self, **payload):
        return self.accept(payload)


def make_event(transport, group=False):
    source_class = botpy.message.GroupMessage if group else botpy.message.C2CMessage
    source = source_class(
        api=transport.api,
        event_id="test-event",
        data={
            "id": "source-message",
            "content": "test",
            "author": {"id": "test-user", "user_openid": "test-user"},
            "group_openid": "test-group" if group else None,
            "timestamp": "2026-10-09T00:00:00Z",
        },
    )
    message = AstrBotMessage()
    message.raw_message = source
    message.message_id = "source-message"
    message.type = MessageType.GROUP_MESSAGE if group else MessageType.FRIEND_MESSAGE
    message.message = []
    message.sender = MessageMember(user_id="test-user", nickname="Test")
    return QQOfficialMessageEvent(
        "test",
        message,
        PlatformMetadata("qq_official", "Test", "test"),
        "test-user",
        SimpleNamespace(api=transport.api),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [False, True])
async def test_real_sender_normalizes_nonstream_markdown(group):
    transport = Transport()
    event = make_event(transport, group)
    chain = MessageChain([Plain(text=SOURCE)], use_markdown_=True)
    await event.send(chain)
    assert list(transport.cards.values()) == [normalize_qq_list_math(SOURCE)]
    assert chain.chain[0].text == SOURCE
    assert transport.frames[0]["msg_type"] == 2
    assert not transport.frames[0].get("stream")


@pytest.mark.asyncio
async def test_real_sender_keeps_plain_text_unmodified():
    transport = Transport()
    event = make_event(transport)
    await event.send(MessageChain([Plain(text=SOURCE)], use_markdown_=False))
    assert transport.frames[0]["msg_type"] == 0
    assert transport.frames[0]["content"] == SOURCE


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_tail", [False, True])
async def test_real_streaming_path_updates_one_complete_card(empty_tail):
    transport = Transport()
    event = make_event(transport)
    prefix = SOURCE if empty_tail else SOURCE[:9]

    async def generate():
        yield MessageChain([Plain(text=prefix)], use_markdown_=True)
        if not empty_tail:
            for character in SOURCE[9:]:
                yield MessageChain([Plain(text=character)], use_markdown_=True)

    await event.send_streaming(generate())
    assert len(transport.frames) == 2
    assert transport.frames[0]["markdown"]["content"] == prefix
    assert transport.frames[0]["stream"]["state"] == 1
    assert transport.frames[-1]["stream"]["state"] == 10
    assert transport.frames[-1]["stream"]["reset"] is True
    assert len(transport.cards) == 1
    expected = normalize_qq_list_math(SOURCE + ("\n" if empty_tail else ""))
    assert list(transport.cards.values()) == [expected]


@pytest.mark.asyncio
async def test_real_streaming_break_does_not_leak_previous_content():
    transport = Transport()
    event = make_event(transport)

    async def generate():
        yield MessageChain([Plain(text=SOURCE)], use_markdown_=True)
        yield MessageChain(type="break")
        yield MessageChain([Plain(text="Next response.")], use_markdown_=True)

    await event.send_streaming(generate())
    assert len(transport.cards) == 2
    assert list(transport.cards.values()) == [
        normalize_qq_list_math(SOURCE + "\n"),
        "Next response.\n",
    ]
    assert transport.frames[-1]["stream"]["state"] == 10
    assert not transport.frames[-1]["stream"].get("reset")


@pytest.mark.asyncio
async def test_real_multiframe_stream_restarts_snapshot_index():
    transport = Transport()
    event = make_event(transport)

    async def generate():
        for index, chunk in enumerate([SOURCE[:5], SOURCE[5:14], SOURCE[14:]]):
            if index:
                await asyncio.sleep(1.05)
            yield MessageChain([Plain(text=chunk)], use_markdown_=True)

    await event.send_streaming(generate())
    assert len(transport.frames) == 4
    assert [frame["stream"]["index"] for frame in transport.frames] == [0, 1, 2, 1]
    assert transport.frames[-1]["stream"]["state"] == 10
    assert transport.frames[-1]["stream"]["reset"] is True
    assert list(transport.cards.values()) == [normalize_qq_list_math(SOURCE + "\n")]


class LimitedTransport(Transport):
    """Mimics QQ: oversized frames and unterminated final md frames fail."""

    LIMIT = 4096

    def accept(self, payload):
        stream = payload.get("stream") or {}
        text = (
            (payload.get("markdown") or {}).get("content")
            or payload.get("content")
            or ""
        )
        if stream and len(text.encode("utf-8")) > self.LIMIT:
            raise botpy.errors.ServerError("流式消息分片过长，请拆分发送")
        if stream.get("state") == 10 and not text.endswith("\n"):
            raise botpy.errors.ServerError("流式消息md分片需要\\n结束")
        return super().accept(payload)


LONG_SOURCE = "".join(
    f"{n}. 第 {n} 步推导：\n   $$\\sigma_{{{n}}} = \\frac{{1}}{{R_x - L^2}}$$\n"
    for n in range(1, 120)
)


@pytest.mark.asyncio
async def test_long_relayout_snapshot_is_split_into_accepted_frames():
    transport = LimitedTransport()
    event = make_event(transport)
    assert len(LONG_SOURCE.encode("utf-8")) > transport.LIMIT

    async def generate():
        step = 1500
        for start in range(0, len(LONG_SOURCE), step):
            if start:
                await asyncio.sleep(1.05)
            yield MessageChain(
                [Plain(text=LONG_SOURCE[start : start + step])], use_markdown_=True
            )

    await event.send_streaming(generate())
    expected = normalize_qq_list_math(LONG_SOURCE + "\n")
    assert expected != LONG_SOURCE + "\n"
    assert list(transport.cards.values()) == [expected]
    resets = [i for i, f in enumerate(transport.frames) if f["stream"].get("reset")]
    assert len(resets) == 1
    tail = transport.frames[resets[0] :]
    assert len(tail) > 1
    assert [f["stream"]["index"] for f in tail] == list(range(1, len(tail) + 1))
    assert [f["stream"]["state"] for f in tail] == [1] * (len(tail) - 1) + [10]


@pytest.mark.asyncio
async def test_oversized_stream_delta_is_split_and_cursor_advances():
    transport = LimitedTransport()
    event = make_event(transport)
    big = "长句子测试。" * 900 + "\n"
    assert len(big.encode("utf-8")) > transport.LIMIT

    async def generate():
        yield MessageChain([Plain(text=big)], use_markdown_=False)
        await asyncio.sleep(1.05)
        yield MessageChain([Plain(text="end")], use_markdown_=False)

    await event.send_streaming(generate())
    assert list(transport.cards.values()) == [big + "end\n"]
    indexes = [f["stream"]["index"] for f in transport.frames]
    assert indexes == list(range(len(indexes)))
    assert transport.frames[-1]["stream"]["state"] == 10


def test_split_stream_text_respects_byte_budget():
    text = "a\n" + "公式" * 700 + "\n" + "b" * 10 + "\n"
    pieces = QQOfficialMessageEvent._split_stream_text(text, 1000)
    assert "".join(pieces) == text
    assert all(len(p.encode("utf-8")) <= 1000 for p in pieces)
    assert QQOfficialMessageEvent._split_stream_text("short", 1000) == ["short"]
