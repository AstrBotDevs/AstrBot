import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from botpy import ConnectionSession
from botpy.errors import ForbiddenError

from astrbot.api.platform import AstrBotMessage, MessageType, PlatformMetadata
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    ManagedBotWebSocket,
    QQOfficialPlatformAdapter,
)
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import (
    QQOfficialWebhookPlatformAdapter,
)
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_server import (
    _SIGNATURE_HEADER,
    _SIGNATURE_TIMESTAMP_HEADER,
    QQOfficialWebhook,
    _sign_qq_webhook_payload,
)

AVATAR_URL = "https://thirdqq.qlogo.cn/bqqthird?key=avatar-key&s=640"


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["websocket", "webhook"])
@pytest.mark.parametrize(
    ("event_name", "author_fields", "nickname", "group_nickname", "avatar"),
    [
        (
            "C2C_MESSAGE_CREATE",
            {"username": "Personal Name", "avatar": AVATAR_URL},
            "Personal Name",
            None,
            AVATAR_URL,
        ),
        ("C2C_MESSAGE_CREATE", {}, "", None, None),
        (
            "GROUP_MESSAGE_CREATE",
            {
                "username": "Personal Name",
                "member_nickname": "Group Name",
                "avatar": AVATAR_URL,
            },
            "Personal Name",
            "Group Name",
            AVATAR_URL,
        ),
        (
            "GROUP_AT_MESSAGE_CREATE",
            {"member_nickname": "Group Name", "avatar": AVATAR_URL},
            "",
            "Group Name",
            AVATAR_URL,
        ),
        (
            "GROUP_MESSAGE_CREATE",
            {"username": "Legacy Name"},
            "Legacy Name",
            None,
            None,
        ),
        ("GROUP_AT_MESSAGE_CREATE", {}, "", None, None),
        (
            "GROUP_MESSAGE_CREATE",
            {"username": None, "member_nickname": "", "avatar": None},
            "",
            None,
            None,
        ),
    ],
)
async def test_qq_sender_profiles_on_inbound_events(
    transport, event_name, author_fields, nickname, group_nickname, avatar, monkeypatch
):
    is_group = event_name != "C2C_MESSAGE_CREATE"
    sender_id = "member-1" if is_group else "user-1"
    group_id = "group-1" if is_group else ""
    author_id_field = "member_openid" if is_group else "user_openid"
    payload = {
        "op": 0,
        "s": 1,
        "t": event_name,
        "id": "event-1",
        "d": {
            "id": "message-1",
            "content": "hello",
            "author": {author_id_field: sender_id, **author_fields},
        },
    }
    if is_group:
        payload["d"]["group_openid"] = group_id
    body = json.dumps(payload)

    config = {
        "id": "qq-test",
        "appid": "123",
        "secret": "secret",
        "enable_group_c2c": True,
        "enable_guild_direct_message": False,
    }
    queue = asyncio.Queue()
    request = AsyncMock(return_value={"group_name": "QQ Group"})
    if transport == "webhook":
        adapter = QQOfficialWebhookPlatformAdapter(config, {}, queue)
        webhook = QQOfficialWebhook(config, queue, adapter.client)
        adapter.webhook_helper = webhook
        monkeypatch.setattr(webhook.http, "request", request)
        timestamp = "1710000000"
        body_bytes = body.encode()
        callback = SimpleNamespace(
            headers={
                _SIGNATURE_TIMESTAMP_HEADER: timestamp,
                _SIGNATURE_HEADER: _sign_qq_webhook_payload(
                    config["secret"], timestamp, body_bytes
                ),
            },
            get_data=AsyncMock(return_value=body_bytes),
        )
        assert await adapter.webhook_callback(callback) == {"opcode": 12}
    else:
        adapter = QQOfficialPlatformAdapter(config, {}, queue)
        monkeypatch.setattr(adapter.client.http, "request", request)
        connection = ConnectionSession(
            max_async=1,
            connect=adapter.client.bot_connect,
            dispatch=adapter.client.ws_dispatch,
            loop=asyncio.get_running_loop(),
            api=adapter.client.api,
        )
        websocket = ManagedBotWebSocket({}, connection, adapter.client)
        await websocket.on_message(None, body)

    event = await asyncio.wait_for(queue.get(), timeout=2)
    assert event.get_sender_name() == nickname
    assert event.get_sender_group_nickname() == group_nickname
    assert event.get_extra("sender_avatar") == avatar
    assert event.get_sender_id() == sender_id
    assert event.get_group_id() == group_id
    assert event.get_session_id() == (group_id or sender_id)
    if is_group:
        assert event.message_obj.group.group_avatar is None
        request.assert_awaited_once()
        assert request.await_args.args[0].path == "/v2/groups/{group_openid}/info"
    else:
        request.assert_not_awaited()

    request.reset_mock()
    profile = {
        "username": "Profile Name",
        "avatar": AVATAR_URL,
        "allow_proactive_msg": False,
        "union_openid": "union-user-1",
    }
    request.return_value = profile
    assert await event.get_user_info("user-1") == profile
    request.assert_awaited_once()
    route = request.await_args.args[0]
    assert route.method == "GET"
    assert route.url == "https://api.bot.qq.com/v2/users/user-1/info"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_openid", "response"),
    [
        ("", None),
        ("user-1", ForbiddenError("No friend relationship")),
        ("user-1", asyncio.TimeoutError()),
        ("user-1", "invalid response"),
        ("user-1", {}),
        ("user-1", {"message": "invalid response"}),
        ("user-1", None),
    ],
)
async def test_user_info_lookup_returns_none_when_unavailable(user_openid, response):
    request = AsyncMock()
    if isinstance(response, Exception):
        request.side_effect = response
    else:
        request.return_value = response
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    event = QQOfficialMessageEvent(
        "",
        message,
        PlatformMetadata(name="qq_official", description="test", id="qq-test"),
        "user-1",
        SimpleNamespace(api=SimpleNamespace(_http=SimpleNamespace(request=request))),
    )

    assert await event.get_user_info(user_openid) is None
    assert request.await_count == int(bool(user_openid))
