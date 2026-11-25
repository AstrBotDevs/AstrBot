"""Native registration and precise WeCom callbacks with HTTP/WS doubles."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.api.event import MessageChain
from astrbot.api.message_components import ActionRow, At, Button, Plain
from astrbot.api.platform import MessageSendReceipt
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_adapter import WecomAIBotAdapter
from astrbot.dashboard.services.config_service import BotConfigService
from astrbot.dashboard.services.platform_service import (
    REGISTRATION_HANDLERS,
    PlatformService,
)


@pytest_asyncio.fixture
async def native_sender(monkeypatch):
    monkeypatch.setattr("astrbot.core.platform.platform.Metric.upload", AsyncMock())
    adapter = WecomAIBotAdapter(
        {
            "id": "wecom-example",
            "wecom_ai_bot_connection_mode": "long_connection",
            "wecomaibot_ws_bot_id": "example-bot",
            "wecomaibot_ws_secret": "example-secret",
        },
        {},
        asyncio.Queue(),
    )
    observed = SimpleNamespace(adapter=adapter, frames=[], ack={"errcode": 0})
    client = adapter.long_connection_client

    async def send_json(payload):
        observed.frames.append(payload)
        if observed.ack is not None:
            await client._handle_text_message(
                json.dumps({"headers": payload["headers"], **observed.ack})
            )

    client._ws = SimpleNamespace(closed=False, send_json=send_json, close=AsyncMock())
    original_wait = client._send_and_wait_response

    async def bounded_wait(request_id, payload):
        return await original_wait(request_id, payload, timeout=0.01)

    monkeypatch.setattr(client, "_send_and_wait_response", bounded_wait)
    yield observed
    await adapter.terminate()


async def received_event(sender, body):
    """Pass through the original callback parser and native event construction."""
    adapter = sender.adapter
    before = set(adapter.queue_mgr.queues)
    await adapter._process_long_connection_payload(
        {
            "cmd": "aibot_msg_callback",
            "headers": {"req_id": "callback-id"},
            "body": body,
        }
    )
    created = set(adapter.queue_mgr.queues) - before
    assert len(created) == 1
    payload = await adapter.queue_mgr.queues[created.pop()].get()
    return adapter.create_event(await adapter.convert_message(payload))


@pytest.mark.asyncio
async def test_public_registration_and_metadata_share_the_actual_dispatch(monkeypatch):
    replies = [
        {
            "data": {
                "scode": "example-code",
                "auth_url": "https://work.weixin.qq.com/ai/qc/example",
            }
        },
        {
            "data": {
                "status": "success",
                "bot_info": {"botid": "example-bot", "secret": "example-secret"},
            }
        },
    ]
    calls = []

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def json(self):
            return replies.pop(0)

    class Http:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr(
        "astrbot.core.platform.sources.wecom_ai_bot.app_registration.aiohttp.ClientSession",
        Http,
    )
    core = SimpleNamespace(platform_manager=None, astrbot_config={"platform": []})
    service = PlatformService(core)
    types = BotConfigService(core).list_bot_types()["registration_types"]
    assert "wecom_ai_bot" in types
    started = await service.handle_platform_registration(
        "wecom_ai_bot", {"action": "start"}
    )
    result = await service.handle_platform_registration(
        "wecom_ai_bot",
        {"action": "poll", "registration_code": started["registration_code"]},
    )
    assert result == {
        "status": "created",
        "wecomaibot_ws_bot_id": "example-bot",
        "wecomaibot_ws_secret": "example-secret",
        "wecom_ai_bot_connection_mode": "long_connection",
    }
    assert all(options["allow_redirects"] is False for _, options in calls)
    assert calls[1][1]["params"] == {"scode": "example-code"}


def test_registration_catalog_is_available_without_loaded_adapters(monkeypatch):
    monkeypatch.setattr(
        "astrbot.dashboard.services.config_service.platform_registry", []
    )
    core = SimpleNamespace(platform_manager=None, astrbot_config={"platform": []})
    config = BotConfigService(core)
    metadata = config.list_bot_types()
    assert metadata["bot_types"] == []
    assert {"weixin_oc", "dingtalk", "wecom_ai_bot"} <= set(
        metadata["registration_types"]
    )
    assert all(
        callable(getattr(PlatformService, REGISTRATION_HANDLERS[kind]))
        for kind in metadata["registration_types"]
    )
    for kind in list(REGISTRATION_HANDLERS):
        monkeypatch.delitem(REGISTRATION_HANDLERS, kind)
    assert config.list_bot_types() == {"bot_types": [], "registration_types": []}
    assert core.astrbot_config["platform"] == []


@pytest.mark.asyncio
async def test_group_addressing_comes_from_current_ordinary_callback(native_sender):
    sender = native_sender
    sender.adapter.bot_name = "Example"
    original = {
        "aibotid": "example-bot",
        "chattype": "group",
        "chatid": "group_with_underscores",
        "msgid": "message-id",
        "from": {"userid": "original-user"},
        "msgtype": "text",
        "text": {"content": "@Example original question"},
        "native_group_mention": "true",
    }
    event = await received_event(sender, original)
    assert event.get_self_id() == "example-bot"
    assert any(
        isinstance(part, At) and part.qq == "example-bot"
        for part in event.get_messages()
    )
    for change in (
        {"aibotid": "other-bot"},
        {"compat_info": None},
        {"compat_info": {}},
    ):
        event = await received_event(sender, {**original, **change})
        assert not any(isinstance(part, At) for part in event.get_messages())


@pytest.mark.asyncio
async def test_text_and_card_use_separate_precise_sends_and_stop_after_unknown(
    native_sender,
):
    sender = native_sender
    event = await received_event(
        sender,
        {
            "aibotid": "example-bot",
            "chattype": "single",
            "msgid": "original-message",
            "from": {"userid": "original_user_with_underscores"},
            "msgtype": "text",
            "text": {"content": "Please confirm"},
        },
    )
    content = "The complete original permission and work description. " * 12
    chain = MessageChain(
        [
            Plain(content),
            ActionRow(
                buttons=[
                    Button(
                        id="confirm",
                        label="Confirm",
                        action=Button.CallbackAction(data={"nonce": "example-nonce"}),
                    )
                ]
            ),
        ]
    )
    receipt = await event.send(chain)
    assert isinstance(receipt, MessageSendReceipt)
    assert [frame["body"]["msgtype"] for frame in sender.frames] == [
        "markdown",
        "template_card",
    ]
    assert sender.frames[0]["body"]["markdown"]["content"] == content.strip()
    assert all(frame["cmd"] == "aibot_send_msg" for frame in sender.frames)
    assert all(
        frame["body"]["chatid"] == "original_user_with_underscores"
        for frame in sender.frames
    )
    assert all(frame["body"]["chat_type"] == 1 for frame in sender.frames)
    assert len({frame["headers"]["req_id"] for frame in sender.frames}) == 2
    sender.frames.clear()
    sender.ack = None
    assert await event.send(chain) is None
    assert len(sender.frames) == 1
