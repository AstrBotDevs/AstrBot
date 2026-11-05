"""Exercise MiniMax discovery and requests through real SDK serialization."""

import json

import pytest
from anthropic import _base_client as anthropic_base_client
from openai import _base_client as openai_base_client

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.minimax_token_plan_source import (
    ProviderMiniMaxTokenPlan,
)
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial

ANTH_HTTPX = getattr(
    anthropic_base_client, "httpx", getattr(anthropic_base_client, "httpx2", None)
)
OPENAI_HTTPX = getattr(
    openai_base_client, "httpx", getattr(openai_base_client, "httpx2", None)
)
PROVIDERS = [ProviderMiniMaxTokenPlan, ProviderAnthropic, ProviderOpenAIOfficial]
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWZkAAAAASUVORK5CYII="


def make_provider(
    monkeypatch,
    provider_cls,
    *,
    base=None,
    model=None,
    extra=None,
    thinking=None,
    key=None,
    discovered=None,
):
    requests = []
    sdk_httpx = OPENAI_HTTPX if provider_cls is ProviderOpenAIOfficial else ANTH_HTTPX

    def handle(request):
        requests.append(request)
        if request.method == "GET":
            return sdk_httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": name,
                            "object": "model",
                            "type": "model",
                            "display_name": name,
                            "created_at": "2026-01-01T00:00:00Z",
                        }
                        for name in (discovered or [])
                    ],
                    "has_more": False,
                },
            )
        payload = json.loads(request.content)
        if provider_cls is ProviderOpenAIOfficial:
            response = {
                "id": "test",
                "object": "chat.completion",
                "created": 1,
                "model": payload["model"],
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
        else:
            response = {
                "id": "test",
                "type": "message",
                "role": "assistant",
                "model": payload["model"],
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        if payload.get("stream"):
            if provider_cls is ProviderOpenAIOfficial:
                chunk = {
                    "id": "test",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": payload["model"],
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                }
                stream = "data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n"
            else:
                start = dict(response, content=[], stop_reason=None)
                events = [
                    {"type": "message_start", "message": start},
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
                stream = "".join(
                    f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
                    for event in events
                )
            return sdk_httpx.Response(
                200, text=stream, headers={"content-type": "text/event-stream"}
            )
        return sdk_httpx.Response(200, json=response)

    monkeypatch.setattr(
        provider_cls,
        "_create_http_client",
        lambda self, config: sdk_httpx.AsyncClient(
            transport=sdk_httpx.MockTransport(handle)
        ),
    )
    config = {"id": "test", "type": "test", "key": [] if key is None else [key]}
    if base is not None:
        config["api_base"] = base
    if model is not None:
        config["model"] = model
    if extra is not None:
        config["custom_extra_body"] = extra
    if thinking is not None:
        config["anth_thinking_config"] = thinking
    return provider_cls(config, {}), requests


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cls", PROVIDERS)
@pytest.mark.parametrize(
    "host", ["api.minimax.cn", "api.minimax.io", "api.minimaxi.com", "api.minimax.chat"]
)
async def test_direct_choices_need_no_discovery_and_preserve_saved_model(
    monkeypatch, provider_cls, host
):
    protocol = "v1" if provider_cls is ProviderOpenAIOfficial else "anthropic"
    provider, requests = make_provider(
        monkeypatch,
        provider_cls,
        base=f"https://{host}/{protocol}",
        model="MiniMax-M2.7",
        # The OpenAI SDK requires a nonempty key even for offline construction.
        key="test-key" if provider_cls is ProviderOpenAIOfficial else None,
    )
    try:
        expected = ["MiniMax-M3.1-Flash"]
        if provider_cls is not ProviderMiniMaxTokenPlan:
            expected.append("MiniMax-M3")
        assert await provider.get_models() == expected
        assert provider.get_model() == "MiniMax-M2.7"
        assert requests == []
        # Caller mutations must not change later discovery.
        choices = await provider.get_models()
        choices.append("custom")
        assert await provider.get_models() == expected
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cls", PROVIDERS)
@pytest.mark.parametrize("host", ["api.minimax.cn", "api.minimax.io"])
@pytest.mark.parametrize("model", [None, "MiniMax-M3", "MiniMax-M2.7", "custom-model"])
async def test_default_and_saved_requests_at_http_boundary(
    monkeypatch, provider_cls, host, model
):
    protocol = "v1" if provider_cls is ProviderOpenAIOfficial else "anthropic"
    provider, requests = make_provider(
        monkeypatch,
        provider_cls,
        base=f"https://{host}/{protocol}",
        model=model,
        key="test-key",
    )
    try:
        result = await provider.text_chat(prompt="hello", system_prompt="system")
        assert result.completion_text == "ok"
        request = requests[-1]
        body = json.loads(request.content)
        assert request.url.host == host
        assert str(request.url).endswith(
            "/chat/completions" if protocol == "v1" else "/v1/messages"
        )
        assert body["model"] == (model or "MiniMax-M3.1-Flash")
        assert "service_tier" not in body
        assert "reasoning_split" not in body
        assert "thinking" not in body
        assert "reasoning_effort" not in body
        assert "output_config" not in body
        if provider_cls is ProviderMiniMaxTokenPlan:
            assert request.headers["Authorization"] == "Bearer test-key"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_subscription_default_region_and_empty_key_list(monkeypatch):
    provider, requests = make_provider(monkeypatch, ProviderMiniMaxTokenPlan)
    try:
        assert provider.base_url == "https://api.minimax.cn/anthropic"
        assert provider.get_model() == "MiniMax-M3.1-Flash"
        assert await provider.get_models() == ["MiniMax-M3.1-Flash"]
        assert requests == []
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cls", PROVIDERS)
async def test_custom_endpoint_keeps_dynamic_discovery_and_explicit_request(
    monkeypatch, provider_cls
):
    provider, requests = make_provider(
        monkeypatch,
        provider_cls,
        base="https://custom.example/v1",
        model="legacy-custom",
        key="test-key",
        discovered=["custom-new", "MiniMax-M2.7"],
    )
    try:
        assert await provider.get_models() == ["MiniMax-M2.7", "custom-new"]
        await provider.text_chat(prompt="hello", model="per-request-custom")
        assert requests[-1].url.host == "custom.example"
        assert json.loads(requests[-1].content)["model"] == "per-request-custom"
        assert provider.get_model() == "legacy-custom"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
async def test_flash_anthropic_effort_and_image_preserved(monkeypatch, effort):
    provider, requests = make_provider(
        monkeypatch,
        ProviderMiniMaxTokenPlan,
        key="test-key",
        thinking={"type": "adaptive", "effort": effort},
        extra={"temperature": 0.7},
    )
    try:
        await provider.text_chat(
            prompt="describe", image_urls=[f"data:image/png;base64,{PNG}"]
        )
        body = json.loads(requests[-1].content)
        assert body["thinking"] == {"type": "adaptive"}
        assert body["output_config"] == {"effort": effort}
        assert body["temperature"] == 0.7
        assert any(
            block["type"] == "image" and block["source"]["data"] == PNG
            for message in body["messages"]
            for block in message["content"]
        )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
async def test_flash_openai_effort_and_image_preserved(monkeypatch, effort):
    provider, requests = make_provider(
        monkeypatch,
        ProviderOpenAIOfficial,
        base="https://api.minimax.io/v1",
        key="test-key",
        extra={"reasoning_effort": effort, "temperature": 0.7},
    )
    try:
        await provider.text_chat(
            prompt="describe", image_urls=[f"data:image/png;base64,{PNG}"]
        )
        body = json.loads(requests[-1].content)
        assert body["reasoning_effort"] == effort
        assert body["temperature"] == 0.7
        assert body["messages"][-1]["content"][-1]["type"] == "image_url"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cls", PROVIDERS)
@pytest.mark.parametrize("streaming", [False, True])
async def test_tools_and_streaming_use_current_default(
    monkeypatch, provider_cls, streaming
):
    protocol = "v1" if provider_cls is ProviderOpenAIOfficial else "anthropic"
    provider, requests = make_provider(
        monkeypatch,
        provider_cls,
        base=f"https://api.minimax.io/{protocol}",
        key="test-key",
    )
    tools = ToolSet(
        [
            FunctionTool(
                name="get_time",
                description="Get time",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )
    try:
        if streaming:
            results = [
                result
                async for result in provider.text_chat_stream(
                    prompt="hello", func_tool=tools
                )
            ]
            assert any(result.completion_text == "ok" for result in results)
        else:
            assert (
                await provider.text_chat(prompt="hello", func_tool=tools)
            ).completion_text == "ok"
        body = json.loads(requests[-1].content)
        assert body["model"] == "MiniMax-M3.1-Flash"
        assert bool(body.get("stream")) == streaming
        tool = body["tools"][0]
        assert (
            tool["function"]["name"] if protocol == "v1" else tool["name"]
        ) == "get_time"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base,discovered,expected",
    [
        (
            "https://openrouter.ai/api/v1",
            [
                "minimax/minimax-m2.7",
                "other/model",
                "minimax/minimax-m3",
                "minimax/minimax-m3.1-flash:free",
            ],
            ["minimax/minimax-m3.1-flash:free", "minimax/minimax-m3", "other/model"],
        ),
        (
            "https://integrate.api.nvidia.com/v1",
            ["minimaxai/minimax-m2.1", "other/model", "minimaxai/minimax-m3"],
            ["minimaxai/minimax-m3", "other/model"],
        ),
        ("https://openrouter.ai/api/v1", ["other/model"], ["other/model"]),
        (
            "https://openrouter.ai/api/v1",
            [
                "minimax/minimax-01",
                "minimax/minimax-media",
                "minimax/minimax-speech",
                "other/model",
            ],
            ["minimax/minimax-media", "minimax/minimax-speech", "other/model"],
        ),
        (
            "https://custom.example/v1",
            ["minimax/minimax-m2.7", "other/model"],
            ["minimax/minimax-m2.7", "other/model"],
        ),
    ],
)
async def test_gateway_catalog_only_filters_minimax_choices(
    monkeypatch, base, discovered, expected
):
    provider, requests = make_provider(
        monkeypatch,
        ProviderOpenAIOfficial,
        base=base,
        key="test-key",
        model="minimax/minimax-m2.7",
        discovered=discovered,
    )
    try:
        assert await provider.get_models() == expected
        await provider.text_chat(prompt="hello")
        assert json.loads(requests[-1].content)["model"] == "minimax/minimax-m2.7"
    finally:
        await provider.terminate()
