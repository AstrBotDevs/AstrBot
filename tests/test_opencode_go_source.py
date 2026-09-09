import asyncio
import hashlib
import json
from functools import partial
from uuid import uuid4

import httpx
import pytest
from anthropic import _base_client as anthropic_base_client
from openai import _base_client as openai_base_client

from astrbot import __version__
from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.message import Message
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.provider.sources.opencode_go_source import (
    ProviderOpenCodeGo,
    ProviderOpenCodeGoMessages,
    ProviderOpenCodeGoResponses,
)


@pytest.fixture
def go_http(monkeypatch):
    """Capture real SDK HTTP requests with deterministic protocol responses."""
    requests = []

    async def handle(request, *, httpx_module):
        requests.append(request)
        await asyncio.sleep(0)
        if request.method == "GET":
            return httpx_module.Response(200, json={"data": [{"id": "kimi-k2.6"}]})
        body = json.loads(request.content)
        model = body["model"]
        if request.url.path.endswith("/chat/completions"):
            response = {
                "id": "chat-1",
                "object": "chat.completion",
                "created": 1,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            }
            events = [
                {
                    **response,
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                }
            ]
        elif request.url.path.endswith("/responses"):
            response = {
                "id": "resp-1",
                "object": "response",
                "created_at": 1,
                "model": model,
                "status": "completed",
                "parallel_tool_calls": True,
                "tool_choice": "auto",
                "tools": [],
                "output": [
                    {
                        "type": "message",
                        "id": "msg-1",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": "ok", "annotations": []}
                        ],
                    }
                ],
            }
            events = [
                {
                    "type": "response.completed",
                    "response": response,
                    "sequence_number": 0,
                }
            ]
        else:
            assert request.url.path == "/zen/go/v1/messages"
            response = {
                "id": "msg-1",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
            events = [
                {
                    "type": "message_start",
                    "message": {**response, "content": [], "stop_reason": None},
                },
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "ok"},
                },
                {"type": "content_block_stop", "index": 0},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 1},
                },
                {"type": "message_stop"},
            ]
        if body.get("stream"):
            content = "".join(
                f"event: {event.get('type', 'message')}\ndata: {json.dumps(event)}\n\n"
                for event in events
            )
            return httpx_module.Response(
                200, text=content, headers={"Content-Type": "text/event-stream"}
            )
        return httpx_module.Response(200, json=response)

    def client(provider, _config):
        sdk = (
            anthropic_base_client
            if isinstance(provider, ProviderAnthropic)
            else openai_base_client
        )
        httpx_module = getattr(sdk, "httpx", getattr(sdk, "httpx2", httpx))
        return httpx_module.AsyncClient(
            transport=httpx_module.MockTransport(
                partial(handle, httpx_module=httpx_module)
            )
        )

    monkeypatch.setattr(ProviderOpenAIOfficial, "_create_http_client", client)
    monkeypatch.setattr(ProviderAnthropic, "_create_http_client", client)
    return requests


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    "provider_class,endpoint",
    [
        (ProviderOpenCodeGo, "chat/completions"),
        (ProviderOpenCodeGoResponses, "responses"),
        (ProviderOpenCodeGoMessages, "messages"),
    ],
)
async def test_go_http_identity_and_concurrent_sessions(
    go_http, provider_class, endpoint, streaming
):
    model = "new-model-without-routing-metadata"
    provider = provider_class(
        {
            "key": ["test-key"],
            "custom_headers": {
                "user-agent": "wrong",
                "X-OpenCode-Session": "wrong",
                "X-Custom": "keep",
            },
        },
        {},
    )
    sessions = [
        str(uuid4()),
        str(uuid4()),
        str(uuid4()),
        str(uuid4()),
    ]

    async def send(conversation_id):
        kwargs = {
            "prompt": "Write a Python function",
            "conversation_id": conversation_id,
            "model": f"opencode-go/{model}",
            "extra_headers": {"X-Request-Test": "request-header"},
        }
        if streaming:
            result = [item async for item in provider.text_chat_stream(**kwargs)]
            assert any(item.completion_text == "ok" for item in result)
        else:
            assert (await provider.text_chat(**kwargs)).completion_text == "ok"

    try:
        await asyncio.gather(*(send(conversation_id) for conversation_id in sessions))
        await send(sessions[0])
        assert len(go_http) == 5
        assert {r.headers["x-opencode-session"] for r in go_http} == {
            hashlib.sha256(conversation_id.encode()).hexdigest()
            for conversation_id in sessions
        }
        assert (
            go_http[-1].headers["x-opencode-session"]
            == hashlib.sha256(sessions[0].encode()).hexdigest()
        )
        assert (
            sum(
                r.headers["x-opencode-session"]
                == go_http[-1].headers["x-opencode-session"]
                for r in go_http
            )
            == 2
        )
        for request in go_http:
            assert request.url.path == f"/zen/go/v1/{endpoint}"
            assert request.headers["user-agent"] == f"AstrBot/{__version__}"
            assert request.headers["x-custom"] == "keep"
            assert request.headers["x-request-test"] == "request-header"
            body = json.loads(request.content)
            assert body["model"] == model
            assert "extra_headers" not in body
            assert "x-opencode-session" not in body
            assert "X-Request-Test" not in body
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_class,endpoint",
    [
        (ProviderOpenCodeGo, "chat/completions"),
        (ProviderOpenCodeGoResponses, "responses"),
        (ProviderOpenCodeGoMessages, "messages"),
    ],
)
async def test_go_model_changes_preserve_selected_protocol(
    go_http, provider_class, endpoint
):
    provider = provider_class({"key": ["test-key"]}, {})
    try:
        assert await provider.get_models() == ["kimi-k2.6"]
        for model in ["kimi-k2.6", "gpt-5.6-luna", "minimax-m3"]:
            provider.set_model(model)
            await provider.text_chat(prompt="Write code")
        assert [r.url.path for r in go_http[1:]] == [f"/zen/go/v1/{endpoint}"] * 3
        assert [json.loads(r.content)["model"] for r in go_http[1:]] == [
            "kimi-k2.6",
            "gpt-5.6-luna",
            "minimax-m3",
        ]
        assert len({r.headers["x-opencode-session"] for r in go_http[1:]}) == 3
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_go_summary_preserves_conversation_conversation_id(go_http):
    provider = ProviderOpenCodeGo({"key": ["test-key"]}, {})
    conversation_id = str(uuid4())
    manager = ContextManager(
        ContextConfig(llm_compress_provider=provider, llm_compress_keep_recent_ratio=0),
        conversation_id=conversation_id,
    )
    try:
        await provider.text_chat(prompt="Write code", conversation_id=conversation_id)
        await manager.compressor(
            [
                Message(role="user", content="Write code"),
                Message(role="assistant", content="Here is the code"),
            ]
        )
        assert len(go_http) == 2
        assert (
            go_http[0].headers["x-opencode-session"]
            == go_http[1].headers["x-opencode-session"]
        )
    finally:
        await provider.terminate()


@pytest.mark.parametrize(
    "name,provider_type,provider_class",
    [
        ("Chat Completions", "opencode_go_chat_completion", ProviderOpenCodeGo),
        ("Responses", "opencode_go_responses", ProviderOpenCodeGoResponses),
        ("Messages", "opencode_go_messages", ProviderOpenCodeGoMessages),
    ],
)
def test_go_templates(name, provider_type, provider_class):
    from astrbot.core.provider.register import provider_cls_map

    template = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ][f"OpenCode Go {name}"]
    assert template["type"] == provider_type
    assert provider_cls_map[provider_type].cls_type is provider_class
    assert template["api_base"] == "https://opencode.ai/zen/go/v1"


@pytest.mark.asyncio
async def test_go_conversation_switch_within_same_umo(go_http):
    provider = ProviderOpenCodeGo({"key": ["test-key"]}, {})
    first_cid, second_cid = str(uuid4()), str(uuid4())
    try:
        for cid in [first_cid, second_cid, first_cid]:
            await provider.text_chat(
                prompt="Write code",
                session_id="qq:GroupMessage:456",
                conversation_id=cid,
            )
        identities = [request.headers["x-opencode-session"] for request in go_http]
        assert identities[0] == identities[2]
        assert identities[0] != identities[1]
        assert identities[0] == hashlib.sha256(first_cid.encode()).hexdigest()
    finally:
        await provider.terminate()
