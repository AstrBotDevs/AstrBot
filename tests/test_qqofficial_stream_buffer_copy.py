"""Regression tests for QQ Official streaming buffer leading-character loss.

Production logs showed group streaming dropping the first delta:
  delta#1 head='不' buf='不'
  delta#2 head='稀' buf='稀'   # wrong, expected '不稀'

Root cause: send_buffer held a reference to the yielded MessageChain; upstream
reused/mutated that object. Fix: _append_stream_delta copies Plain text.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import botpy.message
import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Reply
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.sources.qqofficial import qqofficial_message_event
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
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
        bot=bot,
    )


def _make_c2c_event() -> QQOfficialMessageEvent:
    raw = botpy.message.C2CMessage(
        api=None,
        event_id="event-1",
        data={
            "id": "msg-1",
            "author": {"user_openid": "user-1"},
            "content": "ping",
            "timestamp": "0",
        },
    )
    abm = AstrBotMessage()
    abm.message_id = "msg-1"
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
            _http=SimpleNamespace(request=AsyncMock(return_value={"id": "stream-1"}))
        )
    )
    return QQOfficialMessageEvent(
        message_str="ping",
        message_obj=abm,
        platform_meta=meta,
        session_id="user-1",
        bot=bot,
    )


@pytest.fixture
def stream_clock(monkeypatch):
    """Control only this adapter's clock without changing asyncio globally."""

    def set_ticks(*ticks: float) -> None:
        clock = SimpleNamespace(time=Mock(side_effect=ticks))
        local_asyncio = SimpleNamespace(
            get_running_loop=lambda: clock,
            TimeoutError=asyncio.TimeoutError,
            wait_for=asyncio.wait_for,
            sleep=asyncio.sleep,
        )
        monkeypatch.setattr(qqofficial_message_event, "asyncio", local_asyncio)

    return set_ticks


def _c2c_payloads(event: QQOfficialMessageEvent) -> list[dict]:
    """Read the JSON submitted at the real adapter's HTTP boundary."""
    payloads = [
        call.kwargs["json"] for call in event.bot.api._http.request.await_args_list
    ]
    for payload in payloads:
        assert payload["openid"] == "user-1"
        assert payload["msg_id"] == "msg-1"
    return payloads


def test_append_stream_delta_copies_plain_and_survives_source_mutation() -> None:
    """Unit-level: owned buffer must not track later mutations of the delta."""
    event = _make_group_event()
    shared = MessageChain(chain=[Plain("不")])

    event._append_stream_delta(shared)
    shared.chain[0].text = "稀"  # mutate after append
    event._append_stream_delta(shared)
    shared.chain[0].text = "罕"
    event._append_stream_delta(shared)

    texts = [c.text for c in event.send_buffer.chain if isinstance(c, Plain)]
    assert texts == ["不", "稀", "罕"]
    assert "".join(texts) == "不稀罕"


@pytest.mark.asyncio
async def test_event_contract_resolves_explicit_group_metadata_and_caches_current():
    group_event = _make_group_event()
    current_group = group_event.message_obj.group
    request = AsyncMock(
        side_effect=[
            {"group_name": "Current Group", "group_member_num": 3},
            {"group_name": "Requested Group", "member_count": 7},
        ]
    )
    group_event.bot.api._http = SimpleNamespace(request=request)

    await group_event.send_typing()
    await group_event.stop_typing()
    request.assert_not_awaited()

    assert await group_event.get_group() is current_group
    assert current_group.group_name == "Current Group"
    assert current_group.member_count == 3
    assert await group_event.get_group("group-1") is current_group
    request.assert_awaited_once()

    other_group = await group_event.get_group("different-group")
    assert other_group is not current_group
    assert other_group.group_id == "different-group"
    assert other_group.group_name == "Requested Group"
    assert other_group.member_count == 7
    assert current_group.group_name == "Current Group"
    assert request.await_count == 2
    for call, group_id in zip(
        request.await_args_list, ("group-1", "different-group"), strict=True
    ):
        route = call.args[0]
        assert route.method == "GET"
        assert route.path == "/v2/groups/{group_openid}/info"
        assert route.url.endswith(f"/v2/groups/{group_id}/info")

    private_event = _make_c2c_event()
    assert await private_event.get_group() is None


@pytest.mark.asyncio
async def test_group_stream_keeps_first_character_when_delta_reused() -> None:
    """End-to-end group send_streaming with reused/mutated MessageChain."""
    event = _make_group_event()
    captured: list[str] = []

    async def capture(**kwargs):
        captured.append(_extract_send_text(kwargs))
        return {"id": "out-1"}

    event.bot.api.post_group_message = AsyncMock(side_effect=capture)

    shared = MessageChain(chain=[Plain("不")])

    async def gen():
        shared.chain[0].text = "不"
        yield shared
        shared.chain[0].text = "稀"
        yield shared
        shared.chain[0].text = "罕？"
        yield shared

    await event.send_streaming(gen())

    assert len(captured) == 1
    assert captured[0] == "不稀罕？"


@pytest.mark.asyncio
async def test_group_stream_accumulates_independent_delta_chains() -> None:
    """Normal path: each yield is a fresh MessageChain (openai-style deltas)."""
    event = _make_group_event()
    captured: list[str] = []

    async def capture(**kwargs):
        captured.append(_extract_send_text(kwargs))
        return {"id": "out-1"}

    event.bot.api.post_group_message = AsyncMock(side_effect=capture)

    async def gen():
        yield MessageChain().message("不")
        yield MessageChain().message("稀")
        yield MessageChain().message("罕")
        yield MessageChain().message("？认识。")

    await event.send_streaming(gen())

    assert len(captured) == 1
    assert captured[0] == "不稀罕？认识。"


@pytest.mark.asyncio
async def test_group_stream_preserves_empty_and_multi_char_deltas() -> None:
    event = _make_group_event()
    captured: list[str] = []

    async def capture(**kwargs):
        captured.append(_extract_send_text(kwargs))
        return {"id": "out-1"}

    event.bot.api.post_group_message = AsyncMock(side_effect=capture)

    async def gen():
        yield MessageChain().message("你好")
        yield MessageChain(chain=[Plain("")])
        yield MessageChain().message("\n\n")
        yield MessageChain().message("又来了？")

    await event.send_streaming(gen())

    assert len(captured) == 1
    assert captured[0] == "你好\n\n又来了？"


@pytest.mark.asyncio
async def test_group_stream_keeps_non_plain_components() -> None:
    """A reused reply component must retain its original reference at send time."""
    event = _make_group_event()
    reply = Reply(id="REFIDX_original")
    shared = MessageChain(chain=[Plain("前"), reply])

    async def gen():
        yield shared
        reply.id = "REFIDX_changed"
        shared.chain[:] = [Plain("缀")]
        yield shared

    await event.send_streaming(gen())

    event.bot.api.post_group_message.assert_awaited_once()
    payload = event.bot.api.post_group_message.await_args.kwargs
    assert _extract_send_text(payload) == "前缀"
    assert payload["message_reference"] == {"message_id": "REFIDX_original"}


@pytest.mark.asyncio
async def test_c2c_stream_append_keeps_first_char_before_throttle_flush(
    stream_clock,
) -> None:
    """Buffer reused deltas and serialize one final frame before the throttle."""
    event = _make_c2c_event()
    stream_clock(0.5, 0.5, 0.5)
    shared = MessageChain(chain=[Plain("不")])

    async def gen():
        for text in ("不", "稀", "罕"):
            shared.chain[0].text = text
            yield shared

    await event.send_streaming(gen())

    payloads = _c2c_payloads(event)
    assert len(payloads) == 1
    assert _extract_send_text(payloads[0]) == "不稀罕\n"
    assert payloads[0]["stream"] == {"state": 10, "index": 0, "reset": False}


@pytest.mark.asyncio
async def test_c2c_stream_closes_with_state10_when_tail_buffer_empty(
    stream_clock,
) -> None:
    """Close an open stream even when an intermediate frame consumed all text."""
    event = _make_c2c_event()
    stream_clock(0.5, 2.0, 2.0)

    async def gen():
        yield MessageChain().message("不")
        yield MessageChain().message("稀")

    await event.send_streaming(gen())

    payloads = _c2c_payloads(event)
    assert [
        (payload["stream"]["state"], _extract_send_text(payload))
        for payload in payloads
    ] == [(1, "不稀"), (10, "\n")]
    assert payloads[0]["stream"] == {"state": 1, "index": 0, "reset": False}
    assert payloads[1]["stream"] == {
        "state": 10,
        "id": "stream-1",
        "index": 1,
        "reset": False,
    }


@pytest.mark.asyncio
async def test_c2c_stream_break_closes_open_segment_with_empty_buffer(
    stream_clock,
) -> None:
    """A tool-call break finalizes the open segment without an extra final frame."""
    event = _make_c2c_event()
    stream_clock(2.0, 2.0)

    async def gen():
        yield MessageChain().message("首段文本")
        yield MessageChain(type="break")

    await event.send_streaming(gen())

    payloads = _c2c_payloads(event)
    assert [
        (payload["stream"]["state"], _extract_send_text(payload))
        for payload in payloads
    ] == [(1, "首段文本"), (10, "\n")]
    assert payloads[1]["stream"]["id"] == "stream-1"
    assert payloads[1]["stream"]["index"] == 1


@pytest.mark.asyncio
async def test_group_stream_sends_once_after_all_deltas() -> None:
    event = _make_group_event()
    calls = 0

    async def capture(**kwargs):
        nonlocal calls
        calls += 1
        return {"id": f"out-{calls}"}

    event.bot.api.post_group_message = AsyncMock(side_effect=capture)

    async def gen():
        for ch in "不稀罕":
            yield MessageChain().message(ch)

    await event.send_streaming(gen())
    assert calls == 1


@pytest.mark.asyncio
async def test_c2c_stream_closes_when_tail_is_empty_plain(stream_clock) -> None:
    """An empty Plain delta still requires the final frame for an open stream."""
    event = _make_c2c_event()
    stream_clock(0.5, 2.0, 2.0, 2.0)

    async def gen():
        yield MessageChain().message("不")
        yield MessageChain().message("稀")
        yield MessageChain(chain=[Plain("")])

    await event.send_streaming(gen())

    payloads = _c2c_payloads(event)
    assert [
        (payload["stream"]["state"], _extract_send_text(payload))
        for payload in payloads
    ] == [(1, "不稀"), (10, "\n")]
    assert payloads[1]["stream"]["id"] == "stream-1"
    assert payloads[1]["stream"]["index"] == 1
