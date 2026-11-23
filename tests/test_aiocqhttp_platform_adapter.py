"""Exercise OneBot notice and request conversion without opening a server."""

from types import SimpleNamespace

import pytest
from aiocqhttp import Event

from astrbot.core.message.components import Poke
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.aiocqhttp import aiocqhttp_platform_adapter as module


@pytest.mark.asyncio
@pytest.mark.parametrize("post_type", ["notice", "request"])
@pytest.mark.parametrize("group_id", [None, 42])
async def test_convert_notice_and_request_preserves_sender_and_session(
    monkeypatch, post_type, group_id
):
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: 1700000000))
    monkeypatch.setattr(
        module, "uuid", SimpleNamespace(uuid4=lambda: SimpleNamespace(hex="event-id"))
    )
    payload = {"post_type": post_type, "self_id": 100, "user_id": 7}
    if group_id is not None:
        payload["group_id"] = group_id
    raw = Event(payload)
    adapter = module.AiocqhttpAdapter.__new__(module.AiocqhttpAdapter)

    message = await adapter.convert_message(raw)

    assert message.self_id == "100"
    assert message.sender.user_id == "7"
    assert message.sender.nickname == "7"
    assert message.session_id == ("42" if group_id is not None else "7")
    assert message.type == (
        MessageType.GROUP_MESSAGE
        if group_id is not None
        else MessageType.FRIEND_MESSAGE
    )
    assert message.message == []
    assert message.message_str == ""
    assert message.message_id == "event-id"
    assert message.timestamp == 1700000000
    assert message.raw_message is raw


@pytest.mark.asyncio
async def test_poke_notice_keeps_target_and_group():
    adapter = module.AiocqhttpAdapter.__new__(module.AiocqhttpAdapter)
    raw = Event(
        {
            "post_type": "notice",
            "sub_type": "poke",
            "self_id": 100,
            "user_id": 7,
            "target_id": 88,
            "group_id": 42,
        }
    )

    message = await adapter.convert_message(raw)

    assert message.group_id == "42"
    assert message.session_id == "42"
    assert len(message.message) == 1
    assert isinstance(message.message[0], Poke)
    assert message.message[0].toDict()["data"]["id"] == "88"
