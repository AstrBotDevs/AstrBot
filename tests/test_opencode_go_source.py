from __future__ import annotations

import pytest
from aiohttp import web

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.opencode_go_source import (
    OPENCODE_GO_API_BASE,
    ProviderOpenCodeGo,
)


def test_opencode_go_provider_template():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    template = templates["OpenCode Go"]

    assert template["type"] == "opencode_go_chat_completion"
    assert template["api_base"] == OPENCODE_GO_API_BASE
    assert template["provider_type"] == "chat_completion"


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
