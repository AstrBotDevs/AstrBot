import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer
from fastapi import FastAPI

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.astr_agent_run_util import run_agent
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform.sources.sendblue.sendblue_adapter import SendblueAdapter
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.utils.metrics import Metric
from astrbot.core.utils.webhook_utils import ensure_platform_webhook_config
from astrbot.dashboard.api.platform import get_service, legacy_router
from astrbot.dashboard.services.platform_service import PlatformService
from tests.test_tool_loop_agent_runner import MockProvider

LINE = "+15555550100"
SENDER = "+15555550101"
SECRET = "fixture-webhook-secret"


def event(**changes):
    return {
        "message_handle": "fixture-inbound-1",
        "from_number": SENDER,
        "to_number": LINE,
        "is_outbound": False,
        "status": "RECEIVED",
        "content": "Remember cobalt",
        "group_id": "",
        **changes,
    }


@pytest_asyncio.fixture
async def adapter(monkeypatch):
    monkeypatch.setattr(Metric, "upload", AsyncMock())
    config = dict(
        CONFIG_METADATA_2["platform_group"]["metadata"]["platform"]["config_template"][
            "Sendblue"
        ]
    )
    config.update(
        sendblue_api_key="fixture-key",
        sendblue_api_secret="fixture-secret",
        sendblue_signing_secret=SECRET,
        sendblue_from_number=LINE,
        sendblue_allow_from=[SENDER],
    )
    assert ensure_platform_webhook_config(config)
    # Load through the same registry/import path as normal startup.
    manager = PlatformManager(
        {"platform": [config], "platform_settings": {}}, asyncio.Queue()
    )
    await manager.load_platform(config)
    instance = next(p for p in manager.platform_insts if p.meta().name == "sendblue")
    yield instance
    await manager._terminate_inst_and_tasks(instance)


@pytest_asyncio.fixture
async def client(adapter):
    service = PlatformService(
        SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[adapter]))
    )
    app = FastAPI()
    app.include_router(legacy_router)
    app.dependency_overrides[get_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fixture"
    ) as client:
        yield client


async def post(client, adapter, payload, secret=SECRET):
    return await client.post(
        f"/api/platform/webhook/{adapter.config['webhook_uuid']}",
        json=payload,
        headers={"sb-signing-secret": secret},
    )


@pytest.mark.asyncio
async def test_unified_webhook_to_real_agent_runner_and_reply(adapter, client):
    received = []

    async def provider_endpoint(request):
        assert request.headers["sb-api-key-id"] == "fixture-key"
        assert request.headers["sb-api-secret-key"] == "fixture-secret"
        received.append(await request.json())
        return web.json_response(
            {
                "message_handle": "fixture-outbound-1",
                "status": "QUEUED",
                "error_code": 0,
            }
        )

    app = web.Application()
    app.router.add_post("/api/send-message", provider_endpoint)
    async with TestServer(app) as server:
        await adapter.client.aclose()
        adapter.client = httpx.AsyncClient(
            base_url=str(server.make_url("/")),
            headers={
                "sb-api-key-id": "fixture-key",
                "sb-api-secret-key": "fixture-secret",
            },
        )
        assert (await post(client, adapter, event())).status_code == 200
        incoming = adapter._event_queue.get_nowait()
        assert incoming.get_sender_id() == SENDER
        assert incoming.message_obj.self_id == LINE
        assert incoming.message_obj.message_id == "fixture-inbound-1"
        assert incoming.unified_msg_origin == f"sendblue:FriendMessage:{SENDER}"
        provider = MockProvider()
        provider.text_chat = AsyncMock(
            return_value=LLMResponse(
                role="assistant", completion_text="I remember cobalt."
            )
        )
        runner = ToolLoopAgentRunner()
        await runner.reset(
            provider=provider,
            request=ProviderRequest(prompt=incoming.message_str, contexts=[]),
            run_context=ContextWrapper(context=SimpleNamespace(event=incoming)),
            tool_executor=BaseFunctionToolExecutor(),
            agent_hooks=BaseAgentRunHooks(),
            streaming=False,
        )
        async for chain in run_agent(runner):
            await incoming.send(chain)
        assert received == [
            {"number": SENDER, "from_number": LINE, "content": "I remember cobalt."}
        ]
        assert runner.done()
        assert runner.run_context.messages[-1].role == "assistant"
        assert (await post(client, adapter, event())).status_code == 200
        assert adapter._event_queue.empty()
        await adapter.send_by_session(
            incoming.session, MessageChain().message("Reminder")
        )
        assert received[-1]["content"] == "Reminder"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes,status",
    [
        ({"is_outbound": True}, 200),
        ({"is_outbound": "false"}, 200),
        ({"status": "DELIVERED"}, 200),
        ({"group_id": "group-1"}, 200),
        ({"to_number": "+15555550999"}, 200),
        ({"from_number": "+15555550999"}, 200),
        ({"message_handle": ""}, 400),
        ({"content": {}}, 400),
        ({"media_url": []}, 400),
    ],
)
async def test_filtered_events_never_enter_queue(adapter, client, changes, status):
    assert (await post(client, adapter, event(**changes))).status_code == status
    assert adapter._event_queue.empty()


@pytest.mark.asyncio
async def test_auth_and_size_limit_before_json_parse(adapter, client):
    assert (await post(client, adapter, event(), secret="wrong")).status_code == 401
    assert (await post(client, adapter, [])).status_code == 400

    async def chunks():
        yield b'{"content":"'
        yield b"x" * 65537
        raise AssertionError("The oversized stream must not be consumed further")

    response = await client.post(
        f"/api/platform/webhook/{adapter.config['webhook_uuid']}",
        content=chunks(),
        headers={"sb-signing-secret": SECRET},
    )
    assert response.status_code == 413
    assert adapter._event_queue.empty()


@pytest.mark.asyncio
async def test_backpressure_can_retry_and_media_does_not_download(adapter, client):
    for n in range(128):
        assert (
            await post(client, adapter, event(message_handle=f"m-{n}"))
        ).status_code == 200
    assert (
        await post(client, adapter, event(message_handle="retry"))
    ).status_code == 503
    while not adapter._event_queue.empty():
        adapter._event_queue.get_nowait()
    assert (
        await post(
            client,
            adapter,
            event(
                message_handle="retry",
                content=None,
                media_url="http://169.254.169.254/secret",
            ),
        )
    ).status_code == 200
    incoming = adapter._event_queue.get_nowait()
    assert "supports text only" in incoming.message_str
    assert "169.254" not in incoming.message_str


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        [],
        {},
        {"message_handle": "m", "status": "ERROR"},
        {"message_handle": "m", "status": "QUEUED", "error_code": 400},
    ],
)
async def test_send_requires_provider_acceptance(adapter, result):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=result)

    await adapter.client.aclose()
    adapter.client = httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="https://api.sendblue.com"
    )
    with pytest.raises(RuntimeError, match="did not confirm"):
        await adapter.send_text(SENDER, MessageChain().message("hello"))
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_timeout_is_not_retried_and_chunks_stop(adapter):
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        if len(calls) == 2:
            raise httpx.ReadTimeout("fixture timeout")
        return httpx.Response(200, json={"message_handle": "m", "status": "QUEUED"})

    await adapter.client.aclose()
    adapter.client = httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="https://api.sendblue.com"
    )
    with pytest.raises(RuntimeError, match="unconfirmed"):
        await adapter.send_text(SENDER, MessageChain().message("x" * 4500))
    assert len(calls) == 2
    assert len(calls[0]["content"]) == 2000


def test_missing_credentials_fail_closed():
    with pytest.raises(ValueError, match="requires"):
        SendblueAdapter({}, {}, asyncio.Queue())
