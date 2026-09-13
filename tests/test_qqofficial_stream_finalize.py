"""Regression tests for QQ Official C2C streaming finalisation.

Reported symptom: a streamed C2C reply grew to its full length and then, once
the platform-side stream timed out, the message reverted to the first fragment
(a few characters). The full reply was still stored in the conversation DB.

Root cause: ``send_streaming`` clears ``self.send_buffer`` after every throttled
intermediate send. On normal completion the ``state=10`` final frame was sent
against an already-empty buffer, so ``_post_send`` returned early and the frame
was never delivered -> the C2C stream was never finalised. The ``except`` branch
additionally dropped any unsent tail.

These tests pin the fixed behaviour:
  * an intermediate-throttled send that consumed the whole buffer must still be
    followed by one ``state=10`` frame;
  * when throttling left an unsent tail, the final ``state=10`` frame must carry
    exactly that tail (no duplication);
  * when the upstream stream breaks mid-way, the unsent tail must still be
    flushed with ``state=10`` on the same stream.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

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


def _buffer_text(event: QQOfficialMessageEvent) -> str:
    if not event.send_buffer:
        return ""
    return "".join(c.text for c in event.send_buffer.chain if isinstance(c, Plain))


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


def _capturing_post_send(event: QQOfficialMessageEvent):
    """Return (side_effect, calls) capturing buffer text + stream payload."""
    calls: list[tuple[str, dict | None]] = []

    async def fake_post_send(stream=None):
        # NOTE: send_streaming mutates stream_payload in place, so snapshot it.
        calls.append((_buffer_text(event), dict(stream) if stream else None))
        event.send_buffer = None
        return {"id": f"stream-{len(calls)}"}

    return fake_post_send, calls


@pytest.mark.asyncio
async def test_c2c_stream_is_finalised_when_buffer_already_flushed() -> None:
    """A throttled send that consumed everything must still emit state=10."""
    event = _make_c2c_event()
    fake_post_send, calls = _capturing_post_send(event)

    async def gen():
        yield MessageChain().message("完整回复")

    with (
        patch.object(event, "_post_send", side_effect=fake_post_send),
        patch("asyncio.get_running_loop") as mock_loop,
    ):
        # monotonic time is large, so the first delta triggers a throttled send
        mock_loop.return_value.time.return_value = 100.0
        await event.send_streaming(gen())

    # 1st = throttled state=1 with the whole text; 2nd = empty-tail state=10.
    assert len(calls) == 2
    assert calls[0][1] is not None and calls[0][1]["state"] == 1
    assert calls[0][0] == "完整回复"
    assert calls[1][1] is not None and calls[1][1]["state"] == 10
    # empty tail is delivered as a "\n" marker so _post_send does not drop it
    assert calls[1][0] == "\n"


@pytest.mark.asyncio
async def test_c2c_stream_final_frame_carries_only_unsent_tail() -> None:
    """Content throttled out mid-stream must appear exactly once, in state=10."""
    event = _make_c2c_event()
    fake_post_send, calls = _capturing_post_send(event)

    async def gen():
        yield MessageChain().message("前半")
        yield MessageChain().message("后半")

    with (
        patch.object(event, "_post_send", side_effect=fake_post_send),
        patch("asyncio.get_running_loop") as mock_loop,
    ):
        # constant time: first delta flushes, second is throttled out (no send)
        mock_loop.return_value.time.return_value = 100.0
        await event.send_streaming(gen())

    assert len(calls) == 2
    assert calls[0][1] is not None and calls[0][1]["state"] == 1
    assert calls[0][0] == "前半"
    assert calls[1][1] is not None and calls[1][1]["state"] == 10
    assert calls[1][0] == "后半"


@pytest.mark.asyncio
async def test_c2c_stream_flushes_tail_when_upstream_breaks() -> None:
    """An aborted generator must not leave the stream stuck in state=1."""
    event = _make_c2c_event()
    fake_post_send, calls = _capturing_post_send(event)

    async def gen():
        yield MessageChain().message("前半")
        yield MessageChain().message("后半")
        raise RuntimeError("upstream stream broke")

    with (
        patch.object(event, "_post_send", side_effect=fake_post_send),
        patch("asyncio.get_running_loop") as mock_loop,
    ):
        mock_loop.return_value.time.return_value = 100.0
        await event.send_streaming(gen())

    assert len(calls) == 2
    assert calls[0][1] is not None and calls[0][1]["state"] == 1
    assert calls[1][1] is not None and calls[1][1]["state"] == 10
    assert calls[1][0] == "后半"
