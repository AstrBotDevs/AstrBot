"""Exercise Dify SSE responses through the real client and agent runner."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

from astrbot.core.agent.runners.dify import dify_agent_runner
from astrbot.core.agent.runners.dify.dify_agent_runner import DifyAgentRunner
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party import (
    run_third_party_agent,
)
from astrbot.core.provider.entities import ProviderRequest


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["streaming", "non_streaming", "fallback"])
@pytest.mark.parametrize(
    "events, expected",
    [
        ([("agent_message", "Hello "), ("agent_message", "world")], "Hello world"),
        ([("message", "Hello "), ("message", "world")], "Hello world"),
        (
            [
                ("agent_message", "Hello "),
                ("agent_message", "world"),
                ("message", "Hello world"),
            ],
            "Hello world",
        ),
        ([("agent_message", "Hello "), ("message", "Hello world")], "Hello world"),
        ([("agent_message", "ha"), ("agent_message", "ha")], "haha"),
        ([("message", "ha"), ("message", "ha")], "haha"),
        ([("message", "Thinking."), ("agent_message", "Answer.")], "Thinking.Answer."),
        (
            [
                ("agent_message", "Searching."),
                ("agent_message", "Answer."),
                ("message", "Answer."),
            ],
            "Searching.Answer.",
        ),
        (
            [("agent_message", "Searching.Hello "), ("message", "Hello world")],
            "Searching.Hello world",
        ),
        (
            [("agent_message", "Searching."), ("message", "Answer.")],
            "Searching.Answer.",
        ),
        (
            [("agent_message", "Searching.haha"), ("message", "hahaha!")],
            "Searching.hahaha!",
        ),
        (
            [("agent_message", "检索中。\n你好"), ("message", "你好，世界。")],
            "检索中。\n你好，世界。",
        ),
    ],
)
async def test_dify_answer_replay(monkeypatch, mode, events, expected):
    """Preserve real deltas while removing a cross-event answer replay."""
    requests = []

    async def serve(request):
        requests.append(await request.json())
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        for kind, answer in events:
            frame = {
                "event": kind,
                "answer": answer,
                "message_id": "m1",
                "conversation_id": "c1",
            }
            await response.write(("data: " + json.dumps(frame) + "\n\n").encode())
        await response.write(b'data: {"event": "message_end"}\n\n')
        await response.write_eof()
        return response

    async def get_preference(**kwargs):
        return kwargs["default"]

    monkeypatch.setattr(
        dify_agent_runner,
        "sp",
        SimpleNamespace(get_async=get_preference, put_async=AsyncMock()),
    )
    app = web.Application()
    app.router.add_post("/v1/chat-messages", serve)
    server = web.AppRunner(app)
    await server.setup()
    site = web.TCPSite(server, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    runner = DifyAgentRunner()
    try:
        await runner.reset(
            request=ProviderRequest(prompt="test", session_id="test"),
            run_context=None,
            agent_hooks=SimpleNamespace(
                on_agent_begin=AsyncMock(), on_agent_done=AsyncMock()
            ),
            provider_config={
                "dify_api_base": f"http://127.0.0.1:{port}/v1",
                "dify_api_key": "test",
            },
            streaming=mode != "non_streaming",
        )
        chunks = [
            chain
            async for chain, error in run_third_party_agent(
                runner, stream_to_general=mode == "fallback"
            )
            if not error
        ]
        final = runner.get_final_llm_resp()
        assert final.role == "assistant"
        assert final.result_chain.get_plain_text() == expected
        if mode != "non_streaming":
            assert "".join(chain.get_plain_text() for chain in chunks) == expected
        assert requests[0]["response_mode"] == "streaming"
    finally:
        if hasattr(runner, "api_client"):
            await runner.api_client.close()
        await server.cleanup()
