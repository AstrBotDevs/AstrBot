"""Actual SDK transports verify request-local visual accounting without networking."""

import base64
import copy
import json
import socket
from contextlib import asynccontextmanager
from io import BytesIO

import httpx
import pytest
from anthropic import AsyncAnthropic
from anthropic import _base_client as anthropic_base_client
from google import genai
from google.genai import types
from openai import AsyncOpenAI
from PIL import Image

from astrbot.core.image_request_budget import (
    ImageBudgetExceeded,
    ImageRequestBudget,
    image_payload_size,
)
from astrbot.core.provider.sources import request_retry
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial

KINDS = ["openai", "responses", "anthropic", "gemini"]


@asynccontextmanager
async def sdk_provider(kind, handler):
    """Attach actual SDK serialization to an in-memory HTTP transport.

    Args:
        kind: Provider protocol.
        handler: Deterministic HTTP response factory.

    Yields:
        Provider configured exclusively for an offline mock transport.
    """
    config = {
        "id": kind,
        "type": kind,
        "model": "test-model",
        "key": ["test-key", "other-key"],
        "api_base": "https://offline.invalid/v1",
    }
    classes = {
        "openai": ProviderOpenAIOfficial,
        "responses": ProviderOpenAIResponses,
        "anthropic": ProviderAnthropic,
        "gemini": ProviderGoogleGenAI,
    }
    provider = classes[kind](config, {})
    await provider.terminate()
    sdk_http = (
        getattr(
            anthropic_base_client,
            "httpx2",
            getattr(anthropic_base_client, "httpx", httpx),
        )
        if kind == "anthropic"
        else httpx
    )

    def sdk_handler(request):
        response = handler(request)
        return sdk_http.Response(
            response.status_code, content=response.content, headers=response.headers
        )

    http = sdk_http.AsyncClient(transport=sdk_http.MockTransport(sdk_handler))
    if kind in {"openai", "responses"}:
        provider.client = AsyncOpenAI(
            api_key="test-key",
            base_url=config["api_base"],
            http_client=http,
            max_retries=0,
        )
    elif kind == "anthropic":
        provider.client = AsyncAnthropic(
            api_key="test-key",
            base_url=config["api_base"],
            http_client=http,
            timeout=120,
        )
    else:
        provider.client = genai.Client(
            api_key="test-key",
            http_options=types.HttpOptions(
                base_url=config["api_base"], httpx_async_client=http
            ),
        ).aio
        provider._http_client = http
    try:
        yield provider
    finally:
        await provider.terminate()
        await http.aclose()


def response_body(kind, usage=True):
    if kind == "openai":
        result = {
            "id": "chat1",
            "object": "chat.completion",
            "created": 1,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ],
        }
        result["usage"] = (
            {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
            if usage
            else None
        )
    elif kind == "responses":
        result = {
            "id": "resp1",
            "object": "response",
            "created_at": 1,
            "status": "completed",
            "model": "test-model",
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "output": [
                {
                    "id": "msg1",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {"type": "output_text", "text": "ok", "annotations": []}
                    ],
                }
            ],
        }
        result["usage"] = (
            {
                "input_tokens": 10,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": 2,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 12,
            }
            if usage
            else None
        )
    elif kind == "anthropic":
        result = {
            "id": "msg1",
            "type": "message",
            "role": "assistant",
            "model": "test-model",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 10, "output_tokens": 2} if usage else None,
        }
    else:
        result = {
            "responseId": "gen1",
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": "ok"}]},
                    "finishReason": "STOP",
                }
            ],
        }
        if usage:
            result["usageMetadata"] = {
                "promptTokenCount": 10,
                "candidatesTokenCount": 2,
                "totalTokenCount": 12,
            }
    return result


def payload(kind, count=1):
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(buffer, "PNG")
    data = base64.b64encode(buffer.getvalue()).decode()
    if kind == "responses":
        return {
            "model": "test-model",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": "data:image/png;base64," + data,
                        }
                    ]
                    * count,
                }
            ],
        }
    if kind == "anthropic":
        part = {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": data},
        }
    else:
        part = {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + data},
        }
    return {
        "model": "test-model",
        "messages": [{"role": "user", "content": [part] * count}],
    }


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    def reject_network(*args, **kwargs):
        pytest.fail("External network access is forbidden in SDK budget tests")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_missing_usage_remains_unknown_and_off_path_works(kind):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response_body(kind, usage=False))

    budget = ImageRequestBudget()
    async with sdk_provider(kind, handler) as provider:
        with budget.scope(purpose="main", provider_id=kind, model="test-model"):
            result = await provider._query(payload(kind), None, request_max_retries=1)
        assert result.usage is None
        budget.record_usage(
            result.usage, purpose="main", provider_id=kind, model="test-model"
        )
        before = copy.deepcopy(budget.to_dict())
        off = await provider._query(payload(kind, count=9), None, request_max_retries=1)
        assert off.completion_text == "ok" and budget.to_dict() == before
    assert budget.to_dict()["groups"][0]["unknown_calls"] == 1
    assert len(requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("entrypoint", ["query", "chat", "stream"])
async def test_provider_budget_exhaustion_stops_before_third_sdk_call(kind, entrypoint):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            500,
            json={
                "error": {"message": "temporary", "type": "server_error", "code": 500}
            },
        )

    budget = ImageRequestBudget()
    async with sdk_provider(kind, handler) as provider:
        with budget.scope(purpose="caption", provider_id=kind, model="test-model"):
            with pytest.raises(ImageBudgetExceeded):
                kwargs = {
                    "prompt": "look",
                    "contexts": payload("openai")["messages"],
                    "request_max_retries": 10,
                }
                if entrypoint == "query":
                    await provider._query(payload(kind), None, request_max_retries=10)
                elif entrypoint == "stream":
                    async for _ in provider.text_chat_stream(**kwargs):
                        pass
                else:
                    await provider.text_chat(**kwargs)
    assert len(requests) == budget.caption_attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("reported", [False, True])
@pytest.mark.parametrize("streaming", [False, True])
async def test_sdk_retry_usage_and_final_payload(kind, reported, streaming):
    requests = []
    if not streaming:
        wire = None
    elif kind == "openai":
        packet = {
            "id": "chat1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
        }
        if reported:
            packet["usage"] = response_body(kind)["usage"]
        wire = "data: " + json.dumps(packet) + "\n\ndata: [DONE]\n\n"
    elif kind == "responses":
        packet = {
            "type": "response.completed",
            "sequence_number": 1,
            "response": response_body(kind, usage=reported),
        }
        wire = "data: " + json.dumps(packet) + "\n\n"
    elif kind == "anthropic":
        message = response_body(kind, usage=reported)
        message["content"] = []
        events = [
            {"type": "message_start", "message": message},
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
            {"type": "message_stop"},
        ]
        wire = "".join(
            "event: " + item["type"] + "\ndata: " + json.dumps(item) + "\n\n"
            for item in events
        )
    else:
        wire = "data: " + json.dumps(response_body(kind, usage=reported)) + "\n\n"

    def handler(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                500,
                json={
                    "error": {
                        "message": "temporary",
                        "type": "server_error",
                        "code": 500,
                    }
                },
            )
        if not streaming:
            return httpx.Response(200, json=response_body(kind, usage=reported))
        return httpx.Response(
            200, content=wire, headers={"content-type": "text/event-stream"}
        )

    budget = ImageRequestBudget()
    async with sdk_provider(kind, handler) as provider:
        with budget.scope(purpose="caption", provider_id=kind, model="test-model"):
            if streaming:
                results = [
                    item
                    async for item in provider._query_stream(
                        payload(kind), None, request_max_retries=3
                    )
                ]
                final = results[-1]
            else:
                final = await provider._query(
                    payload(kind), None, request_max_retries=3
                )
            if kind == "anthropic":
                assert provider.client.max_retries == 2
        assert final.completion_text == "ok"
        assert (final.usage is not None) is reported
        budget.record_usage(
            final.usage, purpose="caption", provider_id=kind, model="test-model"
        )
    group = budget.to_dict()["groups"][0]
    assert len(requests) == group["attempts"] == 2
    assert group["unknown_calls"] == (1 if reported else 2)
    if reported:
        assert group["token_usage"]["output"] == 2
    assert (
        sum(image_payload_size(item)[0] for item in requests)
        == group["image_submissions"]
        == 2
    )
    assert (
        sum(image_payload_size(item)[1] for item in requests)
        == group["encoded_bytes"]
        > 0
    )


@pytest.mark.asyncio
async def test_gemini_does_not_retry_after_stream_output(monkeypatch):
    calls = 0

    async def start(**kwargs):
        nonlocal calls
        calls += 1

        async def chunks():
            yield types.GenerateContentResponse(
                candidates=[
                    types.Candidate(
                        content=types.Content(
                            role="model", parts=[types.Part(text="partial")]
                        )
                    )
                ]
            )
            raise httpx.ReadError("Stream interrupted after output")

        return chunks()

    def handler(request):
        pytest.fail("This stream lifecycle test uses a local SDK iterator")

    budget = ImageRequestBudget()
    async with sdk_provider("gemini", handler) as provider:
        monkeypatch.setattr(provider.client.models, "generate_content_stream", start)
        with budget.scope(purpose="caption", provider_id="gemini", model="test-model"):
            stream = provider._query_stream(
                payload("gemini"), None, request_max_retries=10
            )
            assert (await anext(stream)).completion_text == "partial"
            with pytest.raises(httpx.ReadError):
                await anext(stream)
    assert calls == budget.caption_attempts == 1
