from types import SimpleNamespace

import aiohttp
import pytest

from astrbot.core.agent.runners.coze.coze_api_client import CozeAPIClient
from astrbot.core.agent.runners.dashscope.dashscope_agent_runner import (
    DashscopeAgentRunner,
    create_dashscope_http_session,
)
from astrbot.core.agent.runners.deerflow.deerflow_agent_runner import (
    DeerFlowAgentRunner,
)
from astrbot.core.agent.runners.dify.dify_api_client import DifyAPIClient
from astrbot.core.utils.proxy_route import (
    ProxyRoute,
    ProxyRouteMode,
    resolve_proxy_route,
)


class _CapturingResponse:
    def __init__(self, payload: dict | None = None):
        self.status = 200
        self._payload = payload or {"id": "ok"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        _ = exc_type, exc, tb

    async def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _CapturingSession:
    def __init__(self, response: _CapturingResponse | None = None):
        self.calls: list[dict] = []
        self._response = response or _CapturingResponse()

    def post(self, *args, **kwargs):
        _ = args
        self.calls.append(kwargs)
        return self._response

    def get(self, *args, **kwargs):
        _ = args
        self.calls.append(kwargs)
        return self._response

    def delete(self, *args, **kwargs):
        _ = args
        self.calls.append(kwargs)
        return self._response


@pytest.mark.asyncio
async def test_dify_requests_pass_resolved_custom_proxy():
    route = resolve_proxy_route(
        local_config={
            "proxy_mode": "custom",
            "proxy_url": "http://127.0.0.1:7890",
        }
    )
    client = DifyAPIClient("key", proxy_route=route)
    session = _CapturingSession()
    client.session = session
    await client.get_chat_convs("user")
    assert session.calls[0]["proxy"] == "http://127.0.0.1:7890"


@pytest.mark.asyncio
async def test_dify_direct_mode_omits_proxy():
    route = resolve_proxy_route(local_config={"proxy_mode": "direct"})
    client = DifyAPIClient("key", proxy_route=route)
    session = _CapturingSession()
    client.session = session
    await client.get_chat_convs("user")
    assert session.calls[0]["proxy"] is None


@pytest.mark.asyncio
async def test_coze_requests_pass_resolved_proxy():
    route = resolve_proxy_route(
        local_config={
            "proxy_mode": "custom",
            "proxy_url": "http://proxy.example:8080",
        }
    )
    client = CozeAPIClient("key", proxy_route=route)
    session = _CapturingSession(_CapturingResponse(payload={"data": []}))
    client.session = session
    await client.get_message_list("conv-1")
    assert session.calls[0]["proxy"] == "http://proxy.example:8080"


@pytest.mark.asyncio
async def test_coze_direct_mode_omits_proxy():
    route = resolve_proxy_route(local_config={"proxy_mode": "direct"})
    client = CozeAPIClient("key", proxy_route=route)
    session = _CapturingSession(_CapturingResponse(payload={"data": []}))
    client.session = session
    await client.get_message_list("conv-1")
    assert session.calls[0]["proxy"] is None


def test_deerflow_uses_custom_and_direct_proxy_routes():
    runner = DeerFlowAgentRunner()
    custom = runner._parse_runner_config(
        {
            "deerflow_api_base": "http://127.0.0.1:2026",
            "proxy_mode": "custom",
            "proxy_url": "http://127.0.0.1:7890",
        }
    )
    direct = runner._parse_runner_config(
        {
            "deerflow_api_base": "http://127.0.0.1:2026",
            "proxy_mode": "direct",
            "proxy_url": "http://ignored:1",
        }
    )
    assert custom.proxy == "http://127.0.0.1:7890"
    assert direct.proxy == ""


@pytest.mark.asyncio
async def test_dashscope_reset_stores_resolved_proxy_route():
    runner = DashscopeAgentRunner()
    await runner.reset(
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
        {
            "dashscope_api_key": "key",
            "dashscope_app_id": "app",
            "dashscope_app_type": "agent",
            "proxy_mode": "custom",
            "proxy_url": "http://127.0.0.1:7890",
        },
        preferences=SimpleNamespace(),
    )
    try:
        assert runner._proxy_route.mode is ProxyRouteMode.CUSTOM
        assert runner._proxy_route.proxy_url == "http://127.0.0.1:7890"
        session = runner._ensure_http_session()
        assert session.trust_env is False
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_dashscope_routed_session_injects_proxy_and_disables_env(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: list[dict] = []

    async def fake_request(self, method, url, **kwargs):
        _ = self, method, url
        captured.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)
    route = ProxyRoute(
        mode=ProxyRouteMode.CUSTOM,
        proxy_url="http://127.0.0.1:7890",
        no_proxy=(),
        trust_env=False,
        display_proxy="http://127.0.0.1:7890",
    )
    session = create_dashscope_http_session(route)
    try:
        assert session.trust_env is False
        assert session._astrbot_proxy_url == "http://127.0.0.1:7890"
        await session._request("GET", "https://example.test/app")
        assert captured[0]["proxy"] == "http://127.0.0.1:7890"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_dashscope_direct_mode_injects_no_proxy(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: list[dict] = []

    async def fake_request(self, method, url, **kwargs):
        _ = self, method, url
        captured.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)
    route = resolve_proxy_route(local_config={"proxy_mode": "direct"})
    session = create_dashscope_http_session(route)
    try:
        await session._request("POST", "https://example.test/app")
        assert captured[0]["proxy"] is None
        assert session.trust_env is False
    finally:
        await session.close()
