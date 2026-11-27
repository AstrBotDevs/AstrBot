"""Unit tests verifying aiocqhttp ignores inline_keyboard segments at DEBUG level."""

import logging

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)


class _FakeOneBotEvent(dict):
    def __getattr__(self, item: str):
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


def _make_group_event(segments: list[dict]) -> _FakeOneBotEvent:
    return _FakeOneBotEvent(
        {
            "message_type": "group",
            "group_id": 100001,
            "self_id": 900001,
            "message_id": 1001,
            "sender": {"user_id": 10002, "nickname": "OfficialBot"},
            "message": segments,
        }
    )


@pytest.mark.asyncio
async def test_aiocqhttp_inline_keyboard_logged_at_debug_not_warning(caplog):
    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    event = _make_group_event(
        [
            {"type": "text", "data": {"text": "请选择操作"}},
            {
                "type": "inline_keyboard",
                "data": {"rows": [{"buttons": [{"id": "1", "render_data": {"label": "确认"}}]}]},
            },
        ]
    )

    with caplog.at_level(logging.DEBUG, logger="astrbot"):
        abm = await adapter._convert_handle_message_event(event, get_reply=False)

    assert abm.message_str == "请选择操作"
    assert len(abm.message) == 1
    assert isinstance(abm.message[0], Plain)
    assert abm.message[0].text == "请选择操作"

    warning_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert not any("inline_keyboard" in msg for msg in warning_msgs)
    debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("inline_keyboard" in msg for msg in debug_msgs)


@pytest.mark.asyncio
async def test_aiocqhttp_other_unknown_segment_still_warns(caplog):
    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    event = _make_group_event(
        [{"type": "unsupported_custom_xyz", "data": {"foo": "bar"}}]
    )

    with caplog.at_level(logging.WARNING):
        abm = await adapter._convert_handle_message_event(event, get_reply=False)

    assert abm.message == []
    warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("unsupported_custom_xyz" in msg for msg in warning_msgs)
