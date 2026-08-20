"""Regression tests for QQ Official streaming buffer leading-character loss.

Production logs showed group streaming dropping the first delta:
  delta#1 head='不' buf='不'
  delta#2 head='稀' buf='稀'   # wrong, expected '不稀'

Root cause: send_buffer held a reference to the yielded MessageChain; upstream
reused/mutated that object. Fix: _append_stream_delta copies Plain text.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import botpy.message
import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
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
        bot=bot,  # type: ignore[arg-type]
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
    bot = SimpleNamespace(api=SimpleNamespace())
    return QQOfficialMessageEvent(
        message_str="ping",
        message_obj=abm,
        platform_meta=meta,
        session_id="user-1",
        bot=bot,  # type: ignore[arg-type]
    )


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


def test_append_stream_delta_old_reference_style_loses_first_char() -> None:
    """Document the broken pre-fix behavior (reference assign + extend)."""
    event = _make_group_event()
    shared = MessageChain(chain=[Plain("不")])

    # Pre-fix group path:
    #   if not send_buffer: send_buffer = chain
    #   else: send_buffer.chain.extend(chain.chain)
    event.send_buffer = shared
    shared.chain[0].text = "稀"
    event.send_buffer.chain.extend(shared.chain)

    # After mutation + extend-on-self, leading "不" is gone.
    joined = "".join(c.text for c in event.send_buffer.chain if isinstance(c, Plain))
    assert "不" not in joined
    assert joined.startswith("稀")


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
    assert captured[0].startswith("不稀罕？")
    assert "不" in captured[0]


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
    assert captured[0].startswith("不稀罕？认识。")


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
        yield MessageChain().message("\n\n")
        yield MessageChain().message("又来了？")

    await event.send_streaming(gen())

    assert len(captured) == 1
    assert captured[0] == "你好\n\n又来了？"


@pytest.mark.asyncio
async def test_group_stream_keeps_non_plain_components() -> None:
    event = _make_group_event()
    captured_kwargs: list[dict] = []

    async def capture(**kwargs):
        captured_kwargs.append(kwargs)
        return {"id": "out-1"}

    event.bot.api.post_group_message = AsyncMock(side_effect=capture)

    async def gen():
        yield MessageChain().message("前")
        # Image may force media path; still ensure text buffer kept "前缀"
        yield MessageChain(chain=[Plain("缀")])

    await event.send_streaming(gen())

    assert captured_kwargs
    text = _extract_send_text(captured_kwargs[0])
    assert text.startswith("前缀")


@pytest.mark.asyncio
async def test_c2c_stream_append_keeps_first_char_before_throttle_flush() -> None:
    """C2C also uses _append_stream_delta; keep time <1s so only final state=10 sends."""
    event = _make_c2c_event()
    sent_texts: list[str] = []

    async def fake_post_send(stream=None):
        # Capture buffer text at send time (before _post_send clears it).
        parts = []
        if event.send_buffer:
            for c in event.send_buffer.chain:
                if isinstance(c, Plain) and c.text:
                    parts.append(c.text)
        sent_texts.append("".join(parts))
        event.send_buffer = None
        return {"id": f"stream-{len(sent_texts)}"}

    shared = MessageChain(chain=[Plain("不")])

    async def gen():
        shared.chain[0].text = "不"
        yield shared
        shared.chain[0].text = "稀"
        yield shared
        shared.chain[0].text = "罕"
        yield shared

    from unittest.mock import patch

    with (
        patch.object(event, "_post_send", side_effect=fake_post_send),
        patch("asyncio.get_running_loop") as mock_loop,
    ):
        # last_edit_time starts at 0; keep now < 1 so intermediate throttle never fires.
        mock_loop.return_value.time.return_value = 0.5
        await event.send_streaming(gen())

    # Only final state=10 flush with full accumulated text.
    assert len(sent_texts) == 1
    assert sent_texts[0] == "不稀罕"


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
