import asyncio
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

from astrbot.api.message_components import (
    ActionRow,
    Button,
    ButtonInteraction,
    Plain,
)
from astrbot.api.platform import MessageType
from astrbot.core.platform.button_interaction import decode_button_callback
from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent


def test_lark_button_card_maps_callback_and_url_actions():
    card = LarkMessageEvent._build_button_card(
        [
            Plain("Choose an action"),
            ActionRow(
                buttons=[
                    Button(
                        id="approve",
                        label="Approve",
                        action=Button.CallbackAction(data={"request_id": 42}),
                        style=Button.Style.SUCCESS,
                    ),
                    Button(
                        id="docs",
                        label="Docs",
                        action=Button.UrlAction(url="https://example.com/docs"),
                    ),
                ]
            ),
        ],
        MessageType.GROUP_MESSAGE.value,
    )

    assert card["schema"] == "2.0"
    assert card["body"]["elements"][0] == {
        "tag": "markdown",
        "content": "Choose an action",
    }
    columns = card["body"]["elements"][1]["columns"]
    callback_button = columns[0]["elements"][0]
    callback_value = callback_button["behaviors"][0]["value"]
    assert callback_button["type"] == "primary"
    assert decode_button_callback(callback_value["astrbot_callback"]) == (
        "approve",
        {"request_id": 42},
    )
    assert callback_value["astrbot_message_type"] == MessageType.GROUP_MESSAGE.value

    url_button = columns[1]["elements"][0]
    assert url_button["behaviors"] == [
        {
            "type": "open_url",
            "default_url": "https://example.com/docs",
        }
    ]


@pytest.mark.asyncio
async def test_lark_card_callback_becomes_button_interaction():
    adapter = object.__new__(LarkPlatformAdapter)
    adapter.event_id_timestamps = {}
    adapter.bot_open_id = "ou_bot"
    adapter.bot_name = "AstrBot"
    adapter.handle_msg = AsyncMock()
    card = LarkMessageEvent._build_button_card(
        [
            ActionRow(
                buttons=[
                    Button(
                        id="approve",
                        label="Approve",
                        action=Button.CallbackAction(data={"request_id": 42}),
                    )
                ]
            )
        ],
        MessageType.GROUP_MESSAGE.value,
    )
    callback_value = card["body"]["elements"][0]["columns"][0]["elements"][0][
        "behaviors"
    ][0]["value"]

    await adapter.convert_card_action(
        {
            "header": {
                "event_id": "event-1",
                "create_time": "1720000000000000",
            },
            "event": {
                "operator": {"open_id": "ou_user"},
                "action": {"tag": "button", "value": callback_value},
                "context": {
                    "open_message_id": "om_source",
                    "open_chat_id": "oc_group",
                },
            },
        }
    )

    adapter.handle_msg.assert_awaited_once()
    message = adapter.handle_msg.await_args.args[0]
    assert message.type == MessageType.GROUP_MESSAGE
    assert message.session_id == "oc_group"
    assert message.sender.user_id == "ou_user"
    assert message.timestamp == 1720000000
    assert len(message.message) == 1
    interaction = message.message[0]
    assert isinstance(interaction, ButtonInteraction)
    assert interaction.action_id == "approve"
    assert interaction.data == {"request_id": 42}
    assert interaction.interaction_id == "event-1"
    assert interaction.source_message_id == "om_source"


@pytest.mark.asyncio
async def test_lark_socket_card_callback_returns_immediate_ack():
    adapter = LarkPlatformAdapter(
        {
            "id": "lark-test",
            "app_id": "app-id",
            "app_secret": "app-secret",
        },
        {},
        asyncio.Queue(),
    )
    adapter.convert_card_action = AsyncMock()
    callback = P2CardActionTrigger(
        {
            "schema": "2.0",
            "header": {"event_id": "event-1"},
            "event": {},
        }
    )

    response = adapter.do_card_action_trigger(callback)
    await asyncio.sleep(0)

    assert isinstance(response, P2CardActionTriggerResponse)
    adapter.convert_card_action.assert_awaited_once_with(callback)
    adapter.client._cache._cron.cancel()
    await asyncio.gather(adapter.client._cache._cron, return_exceptions=True)


@pytest_asyncio.fixture
async def lark_sdk_transport(monkeypatch):
    """Exercise the generated SDK with only its final HTTP boundary replaced."""
    import json
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import httpx
    import requests
    from lark_oapi.core.token.manager import TokenManager

    from astrbot.core.platform.sources.lark import lark_adapter
    from astrbot.core.utils.metrics import Metric

    class TokenCache:
        def __init__(self):
            self.values = {}

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value, expire):
            self.values[key] = value

    monkeypatch.setattr(TokenManager, "cache", TokenCache())
    monkeypatch.setattr(Metric, "upload", AsyncMock())
    state = {"writes": [], "cards": {}, "next_id": 0, "lose_patch": False}
    calls = []

    def network(request):
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, path, body))
        if request.method == "GET" and "/contact/" in path:
            return httpx.Response(
                200, json={"code": 0, "data": {"user": {"name": "Researcher"}}}
            )
        if request.method == "GET":
            if "user_id_type" in request.url.params:
                state.setdefault("mention_queries", []).append(
                    request.url.params["user_id_type"]
                )
            message = state["cards"].get(path.rsplit("/", 1)[-1])
            return httpx.Response(
                200, json={"code": 0, "data": {"items": [message] if message else []}}
            )
        if state.get("http_error"):
            return httpx.Response(state["http_error"], json=state.get("error_body", {}))
        if request.method == "PATCH":
            message_id = path.rsplit("/", 1)[-1]
            state["cards"][message_id]["body"] = body
            state["writes"].append(("PATCH", message_id, body))
            if state.pop("lose_patch", False):
                raise httpx.ReadTimeout(
                    "accepted update response lost", request=request
                )
            return httpx.Response(200, json={"code": 0, "data": {}})
        if state.get("reject_post") or state.get("reject_after") == len(
            state["writes"]
        ):
            return httpx.Response(200, json={"code": 230035, "msg": "Forbidden"})
        assert request.method == "POST" and "/im/v1/messages" in path
        state["next_id"] += 1
        message_id = f"om_result_{state['next_id']}"
        parent = path.split("/")[-2] if path.endswith("/reply") else None
        message = {
            "message_id": message_id,
            "parent_id": parent,
            "chat_id": "oc_private",
            "msg_type": body["msg_type"],
            "deleted": False,
            "sender": {"sender_type": "app", "id_type": "app_id", "id": "cli_original"},
            "body": {"content": body["content"]},
        }
        state["cards"][message_id] = message
        state["writes"].append(("POST", message_id, body))
        if state.get("omit_code"):
            return httpx.Response(200, json={"data": {"message_id": message_id}})
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {} if state.get("omit_id") else {"message_id": message_id},
            },
        )

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: client_type(
            *args, **kwargs, transport=httpx.MockTransport(network)
        ),
    )

    def token_request(method, url, **kwargs):
        assert method == "POST" and url.endswith(
            "/auth/v3/tenant_access_token/internal"
        )
        return SimpleNamespace(
            status_code=200,
            headers={},
            content=b'{"code":0,"tenant_access_token":"fixture-only","expire":7200}',
        )

    monkeypatch.setattr(requests, "request", token_request)
    preferences = MagicMock()
    preferences.put_async = AsyncMock()
    preferences.get_async = AsyncMock(return_value="oc_private")
    monkeypatch.setattr(lark_adapter, "sp", preferences)
    queue = asyncio.Queue()
    adapter = LarkPlatformAdapter(
        {"id": "lark-original", "app_id": "cli_original", "app_secret": "fixture-only"},
        {},
        queue,
    )
    adapter.bot_open_id = "ou_bot"
    yield adapter, queue, state, calls
    adapter.client._cache._cron.cancel()
    await asyncio.gather(adapter.client._cache._cron, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [None, {"updated": True}, {"chat_id": "oc_other"}])
async def test_lark_group_mentions_load_typed_ids_from_the_original_message(
    lark_sdk_transport, monkeypatch, changed
):
    import json

    import lark_oapi as lark

    from astrbot.core.platform.sources.lark import lark_adapter

    adapter, queue, state, _ = lark_sdk_transport
    monkeypatch.setattr(lark_adapter, "get_lark_group", AsyncMock())
    sender = {"sender_type": "user", "sender_id": {"open_id": "ou_sender"}}
    message = {
        "message_id": "om_mentions",
        "chat_id": "oc_original",
        "chat_type": "group",
        "message_type": "text",
        "content": json.dumps({"text": "@_user_1 @_user_2"}),
        "mentions": [
            {"key": "@_user_1", "id": {"open_id": "ou_human"}, "name": "Teammate"},
            {"key": "@_user_2", "id": {"open_id": "ou_local_bot"}, "name": "Teammate"},
        ],
    }
    typed = [
        {"key": "@_user_1", "id": "ou_human", "id_type": "open_id"},
        {"key": "@_user_2", "id": "cli_other_bot", "id_type": "app_id"},
    ]
    state["cards"]["om_mentions"] = {
        "message_id": "om_mentions",
        "chat_id": "oc_original",
        "deleted": False,
        "updated": False,
        "sender": {"sender_type": "user", "id_type": "open_id", "id": "ou_sender"},
        "mentions": typed,
        **(changed or {}),
    }
    await adapter.convert_msg(
        lark.im.v1.P2ImMessageReceiveV1(
            {"event": {"sender": sender, "message": message}}
        )
    )
    event = queue.get_nowait()
    expected = None if changed else typed
    assert await asyncio.gather(
        event.get_typed_mentions(), event.get_typed_mentions()
    ) == [expected, expected]
    assert event.get_extra("lark_typed_mentions") == expected
    assert state["mention_queries"] == ["open_id"]
    for scene, mentions in (("p2p", message["mentions"]), ("group", [])):
        message.update(chat_type=scene, mentions=mentions)
        await adapter.convert_msg(
            lark.im.v1.P2ImMessageReceiveV1(
                {"event": {"sender": sender, "message": message}}
            )
        )
        assert await queue.get_nowait().get_typed_mentions() == []
    assert state["mention_queries"] == ["open_id"]


@pytest.mark.asyncio
async def test_lark_restored_reply_updates_one_card_then_replies_to_original(
    lark_sdk_transport,
):
    import json
    from dataclasses import asdict

    import httpx
    import lark_oapi as lark

    from astrbot.api.event import MessageChain
    from astrbot.api.platform import MessageReplyContext

    adapter, queue, state, calls = lark_sdk_transport
    incoming = lark.im.v1.P2ImMessageReceiveV1(
        {
            "header": {"tenant_key": "tenant-original"},
            "event": {
                "sender": {
                    "sender_type": "user",
                    "sender_id": {"open_id": "ou_researcher"},
                },
                "message": {
                    "message_id": "om_human",
                    "chat_id": "oc_private",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": '{"text":"Run the calculation"}',
                    "create_time": "1700000000000",
                },
            },
        }
    )
    await adapter.convert_msg(incoming)
    original = queue.get_nowait()
    assert original.get_extra("lark_sender_type") == "user"
    assert original.get_extra("lark_tenant_key") == "tenant-original"
    original.session_id = "oc_private%ou_researcher"
    saved = MessageReplyContext(
        **json.loads(json.dumps(asdict(adapter.get_reply_context(original))))
    )
    assert saved.session_id == "oc_private%ou_researcher"
    assert saved.conversation_id == "oc_private"
    recovered = adapter.create_event(saved)
    assert recovered.get_session_id() == "oc_private%ou_researcher"
    receipt = await recovered.send(
        MessageChain(
            [
                Plain("Review calculation"),
                ActionRow(
                    buttons=[
                        Button(
                            id="approve",
                            label="Approve",
                            action=Button.CallbackAction(data={"proposal": "A"}),
                        )
                    ]
                ),
            ]
        )
    )
    assert receipt.message_ids == ("om_result_1",)
    card = json.loads(state["cards"]["om_result_1"]["body"]["content"])
    value = card["body"]["elements"][1]["columns"][0]["elements"][0]["behaviors"][0][
        "value"
    ]
    await adapter.convert_card_action(
        {
            "header": {"event_id": "action-1"},
            "event": {
                "operator": {"open_id": "ou_researcher"},
                "action": {"tag": "button", "value": value},
                "context": {
                    "open_message_id": "om_result_1",
                    "open_chat_id": "oc_private",
                },
            },
        }
    )
    clicked = queue.get_nowait()
    assert clicked.get_sender_id() == "ou_researcher"
    assert clicked.get_button_interaction().source_message_id == "om_result_1"
    assert clicked.get_button_interaction().interaction_id == "action-1"
    assert clicked.get_button_interaction().data == {"proposal": "A"}

    state["lose_patch"] = True
    with pytest.raises(httpx.ReadTimeout):
        await adapter.update_message(
            saved, "om_result_1", MessageChain([Plain("Approved request 42")])
        )
    result = await adapter.update_message(
        saved, "om_result_1", MessageChain([Plain("Approved request 42")])
    )
    assert result.message_ids == ("om_result_1",)
    final = await adapter.create_event(saved).send(
        MessageChain([Plain("The calculation finished")])
    )
    assert final.message_ids == ("om_result_2",)
    assert [row[:2] for row in state["writes"]] == [
        ("POST", "om_result_1"),
        ("PATCH", "om_result_1"),
        ("PATCH", "om_result_1"),
        ("POST", "om_result_2"),
    ]
    assert state["cards"]["om_result_2"]["parent_id"] == "om_human"
    updated = json.loads(state["cards"]["om_result_1"]["body"]["content"])
    assert updated["body"]["elements"] == [
        {"tag": "markdown", "content": "Approved request 42"}
    ]
    assert not any("cardkit" in path for _, path, _ in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["chat", "app", "deleted"])
async def test_lark_card_update_rejects_a_different_target(lark_sdk_transport, changed):
    from astrbot.api.event import MessageChain
    from astrbot.api.platform import MessageReplyContext, MessageSendRejected

    adapter, _, state, _ = lark_sdk_transport
    saved = MessageReplyContext(
        "lark-original",
        "lark",
        "cli_original",
        "p2p",
        "oc_private",
        "om_human",
        "ou_researcher",
        "ou_researcher",
        1700000000,
    )
    state["cards"]["om_card"] = {
        "message_id": "om_card",
        "chat_id": "oc_private",
        "msg_type": "interactive",
        "deleted": False,
        "sender": {"sender_type": "app", "id_type": "app_id", "id": "cli_original"},
    }
    if changed == "chat":
        state["cards"]["om_card"]["chat_id"] = "oc_other"
    elif changed == "app":
        state["cards"]["om_card"]["sender"]["id"] = "cli_other"
    else:
        state["cards"]["om_card"]["deleted"] = True
    with pytest.raises(MessageSendRejected, match="invalid_target"):
        await adapter.update_message(
            saved, "om_card", MessageChain([Plain("Accepted")])
        )
    assert state["writes"] == []


@pytest.mark.asyncio
async def test_native_lark_buttons_use_a_dedicated_opaque_interaction():
    adapter = object.__new__(LarkPlatformAdapter)
    adapter.event_id_timestamps = {}
    adapter.bot_open_id = "ou_bot"
    adapter.bot_name = "AstrBot"
    adapter.handle_msg = AsyncMock()
    value = {
        "namespace": "example/approval",
        "request_id": "original",
        "action": "approve",
        "astrbot_message_type": MessageType.FRIEND_MESSAGE.value,
    }
    callback = {
        "header": {"event_id": "native-action", "token": "fixture-webhook-token"},
        "event": {
            "operator": {"open_id": "ou_actual"},
            "token": "fixture-card-token",
            "action": {"tag": "button", "value": value},
            "context": {
                "open_message_id": "om_old_card",
                "open_chat_id": "oc_original",
            },
        },
    }
    await adapter.convert_card_action(callback)
    message = adapter.handle_msg.await_args.args[0]
    interaction = message.message[0]
    assert message.type == MessageType.OTHER_MESSAGE
    assert message.session_id == "oc_original"
    assert message.sender.user_id == "ou_actual"
    assert message.raw_message["event"]["context"] == callback["event"]["context"]
    assert "token" not in message.raw_message["header"]
    assert "token" not in message.raw_message["event"]
    assert interaction.action_id == "lark:card_action"
    assert interaction.data == value
    assert interaction.interaction_id == "native-action"
    assert interaction.source_message_id == "om_old_card"
    assert interaction.callback_data is None

    # A malformed AstrBot token must never turn into a native approval action.
    adapter.handle_msg.reset_mock()
    callback["header"]["event_id"] = "invalid-astrbot-action"
    callback["event"]["action"]["value"]["astrbot_callback"] = "invalid"
    await adapter.convert_card_action(callback)
    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_lark_partial_send_is_not_a_whole_chain_rejection(lark_sdk_transport):
    from astrbot.api.event import MessageChain
    from astrbot.api.message_components import At
    from astrbot.api.platform import MessageReplyContext, MessageSendRejected

    adapter, _, state, _ = lark_sdk_transport
    saved = MessageReplyContext(
        "lark-original",
        "lark",
        "cli_original",
        "p2p",
        "oc_private",
        "om_human",
        "ou_researcher",
        "ou_researcher",
        1700000000,
    )
    state["reject_after"] = 1
    with pytest.raises(RuntimeError) as caught:
        await adapter.create_event(saved).send(
            MessageChain(
                [
                    Plain("Choose"),
                    ActionRow(
                        buttons=[
                            Button(
                                id="approve",
                                label="Approve",
                                action=Button.CallbackAction(
                                    data={"request_id": "original"}
                                ),
                            )
                        ]
                    ),
                    At(qq="ou_other"),
                ]
            )
        )
    assert not isinstance(caught.value, MessageSendRejected)
    assert len(state["writes"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["bot", "user"])
async def test_lark_group_removal_uses_the_existing_dispatcher(
    lark_sdk_transport, kind
):
    import hashlib
    import json
    from types import SimpleNamespace

    from lark_oapi.core.model import RawRequest

    from astrbot.core.platform.sources.lark.server import LarkWebhookServer

    adapter, queue, state, calls = lark_sdk_transport
    event_type = f"im.chat.member.{kind}.deleted_v1"
    data = {
        "schema": "2.0",
        "header": {
            "app_id": "cli_original",
            "event_id": "removed-1",
            "event_type": event_type,
            "tenant_key": "tenant-original",
            "create_time": "1700000000000",
        },
        "event": {
            "chat_id": "oc_group",
            "operator_id": {"open_id": "ou_operator"},
            "users": [
                {"user_id": {"open_id": "ou_member"}, "tenant_key": "tenant-original"}
            ],
        },
    }
    request = RawRequest()
    request.uri = "/events"
    request.body = json.dumps(data).encode()
    response = adapter.event_handler.do(request)
    assert response.status_code == 200
    event = await asyncio.wait_for(queue.get(), 1)
    assert event.message_obj.type == MessageType.OTHER_MESSAGE
    assert event.message_obj.message_id == "removed-1"
    assert event.get_group_id() == "oc_group"
    assert event.get_sender_id() == "ou_operator"
    assert event.get_extra("lark_event_type") == event_type
    assert event.message_obj.raw_message["header"]["tenant_key"] == "tenant-original"
    assert event.call_llm is False
    assert not calls and not state["writes"]

    server = LarkWebhookServer(
        {"app_id": adapter.appid, "app_secret": "fixture"}, queue
    )
    server.set_callback(adapter.handle_webhook_event)

    async def deliver_webhook(*, sign=False):
        body = json.dumps(data).encode()
        headers = {}
        if sign:
            headers = {
                "X-Lark-Request-Timestamp": "1700000000",
                "X-Lark-Request-Nonce": "nonce",
                "X-Lark-Signature": hashlib.sha256(
                    b"1700000000noncefixture-key" + body
                ).hexdigest(),
            }
        request = SimpleNamespace(
            headers=headers,
            get_data=AsyncMock(return_value=body),
            json=asyncio.sleep(0, data),
        )
        return await server.handle_callback(request)

    data["header"]["event_id"] = "removed-2"
    assert (await deliver_webhook())[1] == 401
    assert queue.empty()
    server.verification_token = "fixture-token"
    data["header"]["token"] = "fixture-token"
    assert await deliver_webhook() == {}
    received = queue.get_nowait().message_obj
    assert received.message_id == "removed-2"
    assert "token" not in received.raw_message["header"]
    data["header"].update(event_id="foreign-event", app_id="cli_other")
    assert (await deliver_webhook())[1] == 403
    assert queue.empty()
    data["header"].update(event_id="removed-3", app_id=adapter.appid)
    server.encrypt_key = "fixture-key"
    assert (await deliver_webhook())[1] == 401
    assert queue.empty()
    del data["header"]["token"]
    server.verification_token = ""
    assert await deliver_webhook(sign=True) == {}
    assert queue.get_nowait().message_obj.message_id == "removed-3"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["omit_code", "omit_id"])
async def test_lark_unknown_card_result_does_not_send_a_fallback(
    lark_sdk_transport, missing
):
    from astrbot.api.event import MessageChain
    from astrbot.api.platform import MessageReplyContext, MessageSendRejected

    adapter, _, state, calls = lark_sdk_transport
    saved = MessageReplyContext(
        "lark-original",
        "lark",
        "cli_original",
        "p2p",
        "oc_private",
        "om_human",
        "ou_researcher",
        "ou_researcher",
        1700000000,
    )
    state[missing] = True
    with pytest.raises(RuntimeError) as caught:
        await adapter.create_event(saved).send(
            MessageChain([Plain("Progress"), ActionRow(buttons=[])])
        )
    assert not isinstance(caught.value, MessageSendRejected)
    assert len([method for method, path, body in calls if method == "POST"]) == 1
    assert len(state["writes"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body",
    [
        (503, {}),
        (503, {"code": 230034}),
        (200, {}),
        (400, {"code": 230049}),
        (400, {"code": 99991400}),
    ],
)
async def test_lark_uncertain_service_response_never_uses_private_fallback(
    lark_sdk_transport, status, body
):
    from astrbot.api.event import MessageChain
    from astrbot.api.platform import MessageSendRejected
    from astrbot.core.platform.message_session import MessageSession

    adapter, _, state, calls = lark_sdk_transport
    state.update(http_error=status, error_body=body)
    with pytest.raises(RuntimeError) as caught:
        await adapter.send_by_session(
            MessageSession(
                "lark-original", MessageType.FRIEND_MESSAGE, "ou_researcher"
            ),
            MessageChain([Plain("Original result")]),
        )
    assert not isinstance(caught.value, MessageSendRejected)
    assert len([method for method, path, data in calls if method == "POST"]) == 1
