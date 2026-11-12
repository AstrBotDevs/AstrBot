import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import botpy.message
import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import (
    QQOfficialWebhookPlatformAdapter,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapter_class", [QQOfficialPlatformAdapter, QQOfficialWebhookPlatformAdapter]
)
@pytest.mark.parametrize("default", [None, True, False])
@pytest.mark.parametrize("explicit", [None, True, False])
@pytest.mark.parametrize("scene", ["group", "c2c"])
@pytest.mark.parametrize("streaming", [False, True])
async def test_reply_format_preserves_delivery(
    adapter_class, default, explicit, scene, streaming
):
    config = {
        "id": "qq-test",
        "appid": "123",
        "secret": "test-secret",
        "enable_group_c2c": True,
        "enable_guild_direct_message": True,
    }
    if default is not None:
        config["use_markdown"] = default
    adapter = adapter_class(config, {}, asyncio.Queue())
    raw_class = (
        botpy.message.GroupMessage if scene == "group" else botpy.message.C2CMessage
    )
    raw = raw_class(
        api=None,
        event_id="event-1",
        data={
            "id": "msg-1",
            "author": {"member_openid": "user-1", "user_openid": "user-1"},
            "group_openid": "group-1",
            "content": "ping",
            "timestamp": "0",
        },
    )
    message = AstrBotMessage()
    message.message_id = "msg-1"
    message.session_id = "session-1"
    message.sender = MessageMember(user_id="user-1", nickname="User")
    message.type = (
        MessageType.GROUP_MESSAGE if scene == "group" else MessageType.FRIEND_MESSAGE
    )
    message.message_str = "ping"
    message.message = []
    message.raw_message = raw

    payloads = []

    async def capture(**kwargs):
        payloads.append(deepcopy(kwargs))
        return {"id": "sent"}

    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(side_effect=capture)
    )
    event = adapter.create_event(message)
    event.post_c2c_message = AsyncMock(side_effect=capture)
    if streaming:

        async def generate():
            yield MessageChain([Plain("first")], use_markdown_=explicit)
            if scene == "c2c":
                assert len(payloads) == 1
                assert payloads[0]["stream"]["state"] == 1
            else:
                assert not payloads
            yield MessageChain([Plain(" second")], use_markdown_=explicit)

        await event.send_streaming(generate())
    else:
        await event.send(MessageChain([Plain("first second")], use_markdown_=explicit))

    expected_md = (default is not False) if explicit is None else explicit
    texts = []
    for payload in payloads:
        assert payload["msg_type"] == (2 if expected_md else 0)
        if expected_md:
            assert "content" not in payload
            texts.append(payload["markdown"]["content"])
        else:
            assert "markdown" not in payload
            texts.append(payload["content"])
    if streaming and scene == "c2c":
        assert texts == ["first", " second\n"]
        assert payloads[-1]["stream"]["state"] == 10
        assert payloads[-1]["stream"]["id"] == "sent"
    else:
        assert texts == ["first second"]
        assert all("stream" not in payload for payload in payloads)
