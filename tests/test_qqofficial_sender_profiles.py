import asyncio
import json
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer
from botpy import ConnectionSession
from botpy.errors import ForbiddenError, ServerError
from botpy.http import BotHttp
from botpy.manage import C2CManageEvent, GroupManageEvent

from astrbot.api.event import MessageChain
from astrbot.api.message_components import ActionRow, Image, Json, Plain, Reply
from astrbot.api.platform import (
    AstrBotMessage,
    MessageReplyContext,
    MessageSendRejected,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
    _UserInfoRoute,
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
            "Group Name",
            "Group Name",
            AVATAR_URL,
        ),
        (
            "GROUP_AT_MESSAGE_CREATE",
            {"member_nickname": "Group Name", "avatar": AVATAR_URL},
            "Group Name",
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
async def test_user_info_lookup_decodes_json_with_charset_through_botpy(monkeypatch):
    profile = {"username": "Profile Name", "allow_proactive_msg": False}

    async def get_profile(_request):
        return web.Response(
            body=json.dumps(profile).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    app = web.Application()
    app.router.add_get("/v2/users/user-1/info", get_profile)
    async with TestServer(app) as server, ClientSession() as session:
        monkeypatch.setattr(_UserInfoRoute, "SCHEME", "http")
        monkeypatch.setattr(_UserInfoRoute, "DOMAIN", f"{server.host}:{server.port}")
        http = BotHttp(timeout=3)
        http._session = session
        http._token = SimpleNamespace(
            app_id="123",
            check_token=AsyncMock(),
            get_string=lambda: "QQBot local-test",
        )
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.raw_message = None
        event = QQOfficialMessageEvent(
            "",
            message,
            PlatformMetadata(name="qq_official", description="test", id="qq-test"),
            "user-1",
            SimpleNamespace(api=SimpleNamespace(_http=http)),
        )

        assert await event.get_user_info("user-1") == profile


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_openid", "response"),
    [
        ("", None),
        ("user-1", ForbiddenError("No friend relationship")),
        ("user-1", asyncio.TimeoutError()),
        ("user-1", "invalid response"),
        ("user-1", "[]"),
        ("user-1", '{"message": "invalid response"}'),
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
    message.raw_message = None
    event = QQOfficialMessageEvent(
        "",
        message,
        PlatformMetadata(name="qq_official", description="test", id="qq-test"),
        "user-1",
        SimpleNamespace(api=SimpleNamespace(_http=SimpleNamespace(request=request))),
    )

    assert await event.get_user_info(user_openid) is None
    assert request.await_count == int(bool(user_openid))


async def _capture_qq_reply(scene, monkeypatch):
    config = {
        "id": "qq-reply-test",
        "appid": "reply-app",
        "secret": "fixture-secret",
        "enable_group_c2c": True,
        "enable_guild_direct_message": False,
    }
    queue = asyncio.Queue()
    adapter = QQOfficialPlatformAdapter(config, {}, queue)
    request = AsyncMock(return_value={"group_name": "Reply Group"})
    monkeypatch.setattr(adapter.client.http, "request", request)
    connection = ConnectionSession(
        max_async=1,
        connect=adapter.client.bot_connect,
        dispatch=adapter.client.ws_dispatch,
        loop=asyncio.get_running_loop(),
        api=adapter.client.api,
    )
    websocket = ManagedBotWebSocket({}, connection, adapter.client)
    source = {
        "id": "original-human-message",
        "content": "Read the original work",
        "timestamp": datetime.now(UTC).isoformat(),
        "author": {"member_openid" if scene == "group" else "user_openid": "owner-1"},
        "message_scene": {
            "ext": ["msg_idx=REFIDX_original", "ref_msg_idx=REFIDX_parent"]
        },
    }
    if scene == "group":
        source["group_openid"] = "original-group"
    await websocket.on_message(
        None,
        json.dumps(
            {
                "op": 0,
                "s": 1,
                "id": "original-event",
                "t": "GROUP_AT_MESSAGE_CREATE"
                if scene == "group"
                else "C2C_MESSAGE_CREATE",
                "d": source,
            }
        ),
    )
    event = await asyncio.wait_for(queue.get(), timeout=2)
    event.session.session_id = "owner-specific-session"
    context = adapter.get_reply_context(event)
    return adapter, event, context


@pytest.mark.asyncio
@pytest.mark.parametrize("scene", ["group", "c2c"])
async def test_qq_reply_context_survives_restart_without_latest_message(
    scene, monkeypatch
):
    adapter, event, context = await _capture_qq_reply(scene, monkeypatch)
    request = adapter.client.http.request
    request.reset_mock()
    request.return_value = {
        "id": "immediate-result",
        "ext_info": {"ref_idx": "REFIDX_answer"},
    }
    receipt = await event.send(
        MessageChain([Reply(id="original-human-message"), Plain("First answer")])
    )
    assert receipt.message_ids == ("immediate-result",)
    assert receipt.reference_ids == ("REFIDX_answer",)
    assert request.await_count == 1
    assert request.await_args.kwargs["json"]["msg_id"] == "original-human-message"

    saved = MessageReplyContext(**json.loads(json.dumps(asdict(context))))
    restarted = QQOfficialPlatformAdapter(dict(adapter.config), {}, asyncio.Queue())
    restarted.remember_session_scene("owner-specific-session", "guild")
    restarted.remember_session_message_id(
        "owner-specific-session", "new-unrelated-message"
    )
    reply = restarted.create_event(saved)
    request = AsyncMock(
        return_value={"id": "late-result", "ext_info": {"ref_idx": "REFIDX_late"}}
    )
    monkeypatch.setattr(restarted.client.http, "request", request)
    assert reply.get_session_id() == "owner-specific-session"
    assert saved.parent_id == "REFIDX_parent"
    receipt = await reply.send(
        MessageChain([Reply(id="original-human-message"), Plain("Late answer")])
    )
    assert receipt.message_ids == ("late-result",)
    assert receipt.reference_ids == ("REFIDX_late",)
    request.assert_awaited_once()
    route = request.await_args.args[0]
    payload = request.await_args.kwargs["json"]
    assert route.parameters == (
        {"group_openid": "original-group"}
        if scene == "group"
        else {"openid": "owner-1"}
    )
    assert payload["msg_id"] == "original-human-message"
    assert payload["message_reference"] == {"message_id": "REFIDX_original"}
    assert payload["msg_seq"] >= 1
    with pytest.raises(ValueError, match="does not match"):
        restarted.create_event(replace(saved, account_id="another-app"))
    with pytest.raises(ValueError, match="another platform"):
        restarted.get_reply_context(event)


@pytest.mark.asyncio
@pytest.mark.parametrize("scene", ["group", "c2c"])
@pytest.mark.parametrize(
    "outcome",
    [None, asyncio.TimeoutError(), ServerError("unknown"), ForbiddenError("denied")],
)
async def test_qq_restored_reply_does_not_retry_or_change_route(
    scene, outcome, monkeypatch
):
    adapter, _, context = await _capture_qq_reply(scene, monkeypatch)
    request = AsyncMock()
    if isinstance(outcome, Exception):
        request.side_effect = outcome
    else:
        request.return_value = outcome
    monkeypatch.setattr(adapter.client.http, "request", request)
    reply = adapter.create_event(context)
    chain = MessageChain([Plain("The original result")])
    if isinstance(outcome, ForbiddenError):
        with pytest.raises(MessageSendRejected, match="permission_denied"):
            await reply.send(chain)
    elif isinstance(outcome, Exception):
        with pytest.raises(type(outcome)):
            await reply.send(chain)
    else:
        assert await reply.send(chain) is None
    request.assert_awaited_once()
    assert request.await_args.kwargs["json"]["msg_id"] == context.message_id
    assert reply.send_buffer is None


@pytest.mark.asyncio
@pytest.mark.parametrize("scene", ["group", "c2c"])
async def test_qq_expired_reply_requires_explicit_proactive_choice(scene, monkeypatch):
    adapter, _, context = await _capture_qq_reply(scene, monkeypatch)
    expired = replace(context, timestamp=int(time.time()) - 7200)
    request = AsyncMock(return_value={"id": "late-result"})
    monkeypatch.setattr(adapter.client.http, "request", request)
    with pytest.raises(MessageSendRejected, match="reply_window_expired"):
        await adapter.create_event(expired).send(MessageChain([Plain("Result")]))
    request.assert_not_awaited()
    receipt = await adapter.create_event(replace(expired, mode="proactive")).send(
        MessageChain([Plain("Result")])
    )
    assert receipt.message_ids == ("late-result",)
    request.assert_awaited_once()
    assert request.await_args.kwargs["json"].get("msg_id") is None
    assert request.await_args.args[0].parameters == (
        {"group_openid": "original-group"}
        if scene == "group"
        else {"openid": "owner-1"}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type",
    [
        "C2C_MSG_RECEIVE",
        "C2C_MSG_REJECT",
        "FRIEND_ADD",
        "FRIEND_DEL",
        "GROUP_ADD_ROBOT",
        "GROUP_DEL_ROBOT",
    ],
)
async def test_qq_native_permission_event_preserves_source_without_replacing_last_message(
    event_type,
):
    queue = asyncio.Queue()
    adapter = QQOfficialPlatformAdapter(
        {
            "id": "qq-notice-test",
            "appid": "notice-app",
            "secret": "fixture-secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        queue,
    )
    adapter.remember_session_message_id("original-owner", "original-human-message")
    connection = ConnectionSession(
        max_async=1,
        connect=adapter.client.bot_connect,
        dispatch=adapter.client.ws_dispatch,
        loop=asyncio.get_running_loop(),
        api=adapter.client.api,
    )
    websocket = ManagedBotWebSocket({}, connection, adapter.client)
    occurred_at = int(time.time()) - 20
    group = event_type.startswith("GROUP_")
    await websocket.on_message(
        None,
        json.dumps(
            {
                "op": 0,
                "s": 1,
                "t": event_type,
                "id": "native-permission-event",
                "d": {
                    "timestamp": occurred_at,
                    **(
                        {
                            "group_openid": "original-group",
                            "op_member_openid": "original-owner",
                        }
                        if group
                        else {"openid": "original-owner"}
                    ),
                },
            }
        ),
    )
    event = await asyncio.wait_for(queue.get(), timeout=2)
    assert event.get_message_type() == MessageType.OTHER_MESSAGE
    assert event.get_extra("qq_official_event") == event_type
    assert event.get_sender_id() == "original-owner"
    assert event.get_self_id() == "notice-app"
    assert event.message_obj.message_id == "native-permission-event"
    assert event.message_obj.timestamp == occurred_at
    assert isinstance(
        event.message_obj.raw_message, GroupManageEvent if group else C2CManageEvent
    )
    if group:
        assert event.get_group_id() == "original-group"
        assert event.message_obj.raw_message.op_member_openid == "original-owner"
    else:
        assert event.message_obj.raw_message.openid == "original-owner"
    assert event.is_at_or_wake_command is False
    assert not event.message_str and not event.get_messages()
    assert (
        adapter._session_last_message_id["original-owner"] == "original-human-message"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "components",
    [
        [Json({"unsupported": True})],
        [Image.fromBase64("aGVsbG8=")],
        [Reply(id="different-human-message")],
        [Reply(id="original-human-message"), Reply(id="REFIDX_another")],
        [ActionRow(buttons=[], fallback_text="Unsent action")],
    ],
)
async def test_qq_partial_content_does_not_receive_a_complete_chain_receipt(
    components, monkeypatch
):
    adapter, event, _ = await _capture_qq_reply("group", monkeypatch)
    request = AsyncMock(return_value={"id": "text-part-accepted"})
    monkeypatch.setattr(adapter.client.http, "request", request)
    monkeypatch.setattr(
        event, "upload_group_and_c2c_image", AsyncMock(return_value=None)
    )
    assert await event.send(MessageChain([Plain("Text part"), *components])) is None
    request.assert_awaited_once()
