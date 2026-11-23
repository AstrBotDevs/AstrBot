from __future__ import annotations

import httpx
import pytest
from aiohttp import web

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources import request_retry
from astrbot.core.provider.sources.opencode_go_source import (
    _MAX_TRACKED_SESSIONS,
    OPENCODE_GO_API_BASE,
    ProviderOpenCodeGo,
)


def _make_provider(**overrides) -> ProviderOpenCodeGo:
    provider_config = {
        "id": "test-opencode-go",
        "type": "opencode_go_chat_completion",
        "model": "kimi-k3",
        "key": ["test-key"],
    }
    provider_config.update(overrides)
    return ProviderOpenCodeGo(provider_config, {})


def test_opencode_go_provider_template():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    template = templates["OpenCode Go"]

    assert template["type"] == "opencode_go_chat_completion"
    assert template["api_base"] == OPENCODE_GO_API_BASE
    assert template["provider_type"] == "chat_completion"


@pytest.mark.asyncio
@pytest.mark.parametrize("api_base", ["", "   ", None])
async def test_opencode_go_empty_api_base_falls_back_to_default(api_base):
    provider = _make_provider(api_base=api_base)
    try:
        assert str(provider.client.base_url).startswith(OPENCODE_GO_API_BASE)
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_go_session_counters_are_bounded():
    provider = _make_provider(api_base=OPENCODE_GO_API_BASE)
    try:
        for index in range(_MAX_TRACKED_SESSIONS + 10):
            provider._opencode_session_headers(f"conversation-{index}")

        assert len(provider._session_request_counts) == _MAX_TRACKED_SESSIONS
        assert "conversation-0" not in provider._session_request_counts
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_go_transport_retry_reuses_request_identity(monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    provider = _make_provider(api_base=OPENCODE_GO_API_BASE)
    calls: list[dict] = []

    class FakeCompletions:
        def __init__(self):
            self.attempts = 0

        async def create(self, **kwargs):
            calls.append(kwargs)
            self.attempts += 1
            if self.attempts == 1:
                raise httpx.ConnectError("temporary connection failure")
            return "completion"

    monkeypatch.setattr(provider.client.chat, "completions", FakeCompletions())
    try:
        created = await provider._send_opencode_request(
            {"model": "kimi-k3", "messages": []},
            None,
            stream=False,
            request_max_retries=2,
            conversation_id="conversation-1",
        )

        assert created == "completion"
        assert len(calls) == 2
        assert calls[0]["extra_headers"] == calls[1]["extra_headers"]
        assert calls[0]["extra_headers"]["x-opencode-request"] == "msg_1"
        assert calls[0]["extra_headers"]["x-opencode-session"] == "conversation-1"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_go_sends_user_agent_and_session_id(
    unused_tcp_port, monkeypatch
):
    requests = []

    async def handle(request):
        requests.append(request)
        return web.json_response(
            {
                "id": "chatcmpl_test",
                "object": "chat.completion",
                "created": 1,
                "model": "kimi-k3",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        )

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handle)
    runner = web.AppRunner(app)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
        provider = ProviderOpenCodeGo(
            {
                "id": "test-opencode-go",
                "type": "opencode_go_chat_completion",
                "model": "kimi-k3",
                "key": ["test-key"],
                "api_base": f"http://127.0.0.1:{unused_tcp_port}/v1",
            },
            {},
        )
        try:
            response = await provider._query(
                {"model": "kimi-k3", "messages": [{"role": "user", "content": "hi"}]},
                None,
                conversation_id="stable-conversation-id",
            )
            assert response.completion_text == "ok"
            assert len(requests) == 1
            assert requests[0].headers["User-Agent"].startswith("astrbot/")
            assert requests[0].headers["x-opencode-session"] == "stable-conversation-id"
            assert "x-astrbot-conversation-id" not in requests[0].headers
        finally:
            await provider.terminate()
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_opencode_go_one_off_requests_use_stable_session_id(
    unused_tcp_port, monkeypatch
):
    requests = []

    async def handle(request):
        requests.append(request)
        return web.json_response(
            {
                "id": "chatcmpl_test",
                "object": "chat.completion",
                "created": 1,
                "model": "kimi-k3",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        )

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handle)
    runner = web.AppRunner(app)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
        provider = ProviderOpenCodeGo(
            {
                "id": "test-opencode-go-one-off",
                "type": "opencode_go_chat_completion",
                "model": "kimi-k3",
                "key": ["test-key"],
                "api_base": f"http://127.0.0.1:{unused_tcp_port}/v1",
            },
            {},
        )
        try:
            payload = {
                "model": "kimi-k3",
                "messages": [{"role": "user", "content": "hi"}],
            }
            await provider._query(dict(payload), None)
            await provider._query(dict(payload), None)

            assert len(requests) == 2
            session_ids = [
                request.headers.get("x-opencode-session") for request in requests
            ]
            assert all(session_ids)
            assert session_ids[0] == session_ids[1]
            assert requests[0].headers["x-opencode-request"] == "msg_1"
            assert requests[1].headers["x-opencode-request"] == "msg_2"
            for request in requests:
                assert request.headers["x-opencode-client"] == "cli"
                assert request.headers["x-opencode-project"] == "global"
        finally:
            await provider.terminate()
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_opencode_go_model_list_sends_session_id(unused_tcp_port, monkeypatch):
    requests = []

    async def handle(request):
        requests.append(request)
        return web.json_response(
            {
                "object": "list",
                "data": [
                    {"id": "beam-free", "object": "model", "created": 1},
                    {"id": "claude-haiku-5-5", "object": "model", "created": 1},
                ],
            }
        )

    app = web.Application()
    app.router.add_get("/v1/models", handle)
    runner = web.AppRunner(app)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
        provider = ProviderOpenCodeGo(
            {
                "id": "test-opencode-go-models",
                "type": "opencode_go_chat_completion",
                "model": "kimi-k3",
                "key": ["test-key"],
                "api_base": f"http://127.0.0.1:{unused_tcp_port}/v1",
            },
            {},
        )
        try:
            models = await provider.get_models()

            assert models == ["beam-free", "claude-haiku-5-5"]
            assert requests[0].headers.get("x-opencode-session")
        finally:
            await provider.terminate()
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_opencode_go_stream_sends_session_id(unused_tcp_port, monkeypatch):
    requests = []

    async def handle(request):
        requests.append(request)
        response = web.StreamResponse(
            headers={"Content-Type": "text/event-stream"},
        )
        await response.prepare(request)
        await response.write(
            b'data: {"id":"chunk_1","object":"chat.completion.chunk","created":1,'
            b'"model":"kimi-k3","choices":[{"index":0,"delta":{"content":"ok"},'
            b'"finish_reason":null}]}\n\n'
        )
        await response.write(
            b'data: {"id":"chunk_2","object":"chat.completion.chunk","created":1,'
            b'"model":"kimi-k3","choices":[{"index":0,"delta":{},'
            b'"finish_reason":"stop"}]}\n\n'
        )
        await response.write(b"data: [DONE]\n\n")
        return response

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handle)
    runner = web.AppRunner(app)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
        provider = ProviderOpenCodeGo(
            {
                "id": "test-opencode-go-stream",
                "type": "opencode_go_chat_completion",
                "model": "kimi-k3",
                "key": ["test-key"],
                "api_base": f"http://127.0.0.1:{unused_tcp_port}/v1",
            },
            {},
        )
        try:
            results = [
                result
                async for result in provider._query_stream(
                    {
                        "model": "kimi-k3",
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                    None,
                    conversation_id="stable-stream-session",
                )
            ]
            assert results[-1].completion_text == "ok"
            assert len(requests) == 1
            assert requests[0].headers["x-opencode-session"] == "stable-stream-session"
        finally:
            await provider.terminate()
    finally:
        await runner.cleanup()
