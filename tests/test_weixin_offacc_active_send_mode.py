"""Active send mode must not require a passive-reply buffer in create_event."""

import asyncio

import pytest

from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter import (
    WeixinOfficialAccountPlatformAdapter,
)


def _adapter(**overrides) -> WeixinOfficialAccountPlatformAdapter:
    config = {
        "id": "weixin_offacc_test",
        "appid": "a",
        "secret": "s",
        "port": 6199,
        "token": "t",
        "encoding_aes_key": "a" * 43,
        **overrides,
    }
    return WeixinOfficialAccountPlatformAdapter(config, {}, asyncio.Queue())


def _message() -> AstrBotMessage:
    abm = AstrBotMessage()
    abm.message_str = "hi"
    abm.message_id = "1"
    abm.type = MessageType.FRIEND_MESSAGE
    abm.self_id = "gh_test"
    abm.session_id = "user1"
    abm.sender = MessageMember(user_id="user1", nickname="user1")
    abm.raw_message = {}
    return abm


@pytest.mark.asyncio
async def test_active_send_mode_creates_event_without_buffer():
    adapter = _adapter(active_send_mode=True)
    event = adapter.create_event(_message())
    assert event.message_out == {}


@pytest.mark.asyncio
async def test_passive_mode_still_requires_buffer():
    adapter = _adapter(active_send_mode=False)
    with pytest.raises(ValueError, match="User message buffer not found"):
        adapter.create_event(_message())
