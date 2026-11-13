import asyncio
import hashlib
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest
from anthropic.types import Message as AnthropicMessage
from google.genai import types as genai_types
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.responses import Response as OpenAIResponse

import astrbot.core.provider.sources.request_retry as request_retry
from astrbot import __version__
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial

UMO = "aiocqhttp:GroupMessage:100"
CUSTOM_HEADERS = {
    "x-session": "{sha256:{conversation_id}}",
    "x-umo": "{umo}",
    "x-umo-uuid": "{uuid5:{umo}}",
    "x-request": "{request_id}",
    "x-model": "{model}",
    "x-provider": "{provider_id}",
    "x-version": "{version}",
    "X-Astrbot-Conversation-Id": "spoofed",
}


def _expected_headers(conversation_id="cid-1", model="gpt-4o", request_id="rid-1"):
    return {
        "x-session": hashlib.sha256(conversation_id.encode()).hexdigest(),
        "x-umo": UMO,
        "x-umo-uuid": str(uuid5(NAMESPACE_URL, "astrbot:provider-header:" + UMO)),
        "x-request": request_id,
        "x-model": model,
        "x-provider": "provider-1",
        "x-version": __version__,
        "x-astrbot-conversation-id": conversation_id,
    }


def _sent_headers(static_headers, request_headers):
    """Merge SDK default headers with per-request headers like the SDK does."""
    sent = {**static_headers, **request_headers}
    sent.pop("User-Agent", None)
    return sent


def _chat_completion(text="ok"):
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-4o",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )


def _chat_chunks(text="ok"):
    return [
        ChatCompletionChunk.model_validate(
            {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": text},
                        "finish_reason": None,
                    }
                ],
            }
        ),
        ChatCompletionChunk.model_validate(
            {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "gpt-4o",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        ),
    ]


def _openai_provider():
    return ProviderOpenAIOfficial(
        {
            "id": "provider-1",
            "type": "openai_chat_completion",
            "model": "gpt-4o-mini",
            "key": ["test-key"],
            "custom_headers": dict(CUSTOM_HEADERS),
        },
        {},
    )


async def _openai_text_chat_with_capture(monkeypatch, **chat_kwargs):
    provider = _openai_provider()
    captured: list[dict] = []

    async def fake_create(**kwargs):
        captured.append(kwargs)
        return _chat_completion()

    monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)
    try:
        response = await provider.text_chat(prompt="hi", **chat_kwargs)
    finally:
        await provider.terminate()
    return provider, captured, response


@pytest.mark.asyncio
async def test_openai_text_chat_sends_rendered_request_headers(monkeypatch):
    provider, captured, response = await _openai_text_chat_with_capture(
        monkeypatch,
        umo=UMO,
        conversation_id="cid-1",
        request_id="rid-1",
        model="gpt-4o",
    )

    assert response.completion_text == "ok"
    assert _sent_headers(provider.custom_headers, captured[0]["extra_headers"]) == (
        _expected_headers()
    )
    # Dynamic templates must never reach SDK default headers.
    assert "x-session" not in provider.custom_headers
    assert "x-astrbot-conversation-id" not in provider.custom_headers


@pytest.mark.asyncio
async def test_openai_text_chat_omits_headers_with_missing_values(monkeypatch):
    provider = _openai_provider()
    captured: list[dict] = []

    async def fake_create(**kwargs):
        captured.append(kwargs)
        return _chat_completion()

    monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)
    try:
        await provider.text_chat(prompt="hi", request_id="rid-1")
    finally:
        await provider.terminate()

    headers = captured[0]["extra_headers"]
    assert "x-umo" not in headers
    assert "x-umo-uuid" not in headers
    assert "x-astrbot-conversation-id" not in headers
    assert headers["x-request"] == "rid-1"
    # {conversation_id} falls back to the request ID.
    assert headers["x-session"] == hashlib.sha256(b"rid-1").hexdigest()
    assert provider._omitted_header_logs == {"x-umo", "x-umo-uuid"}


@pytest.mark.asyncio
async def test_openai_text_chat_reuses_headers_across_transport_retries(monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)

    provider = _openai_provider()
    captured: list[dict] = []
    attempts = 0

    async def fake_create(**kwargs):
        nonlocal attempts
        attempts += 1
        captured.append(kwargs)
        if attempts == 1:
            raise httpx.ConnectError("temporary connection failure")
        return _chat_completion()

    monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)
    try:
        await provider.text_chat(
            prompt="hi",
            umo=UMO,
            conversation_id="cid-1",
            request_id="rid-1",
            request_max_retries=2,
        )
    finally:
        await provider.terminate()

    assert attempts == 2
    assert captured[0]["extra_headers"] == captured[1]["extra_headers"]
    assert _sent_headers(provider.custom_headers, captured[1]["extra_headers"]) == (
        _expected_headers(model="gpt-4o-mini")
    )


@pytest.mark.asyncio
async def test_openai_text_chat_generates_distinct_request_ids_without_one(monkeypatch):
    provider = _openai_provider()
    captured: list[dict] = []

    async def fake_create(**kwargs):
        captured.append(kwargs)
        return _chat_completion()

    monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)
    try:
        await provider.text_chat(prompt="hi", session_id=UMO)
        await provider.text_chat(prompt="hi again", session_id=UMO)
    finally:
        await provider.terminate()

    first, second = (item["extra_headers"]["x-request"] for item in captured)
    assert first != second
    for item in captured:
        headers = item["extra_headers"]
        assert "x-astrbot-conversation-id" not in headers
        # The deprecated session_id parameter must not leak as {umo}.
        assert "x-umo" not in headers
        assert "x-umo-uuid" not in headers
        assert (
            headers["x-session"]
            == hashlib.sha256(headers["x-request"].encode()).hexdigest()
        )


@pytest.mark.asyncio
async def test_openai_text_chat_stream_sends_rendered_request_headers(monkeypatch):
    provider = _openai_provider()
    captured: list[dict] = []

    async def fake_stream():
        for chunk in _chat_chunks():
            yield chunk

    async def fake_create(**kwargs):
        captured.append(kwargs)
        return fake_stream()

    monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)
    try:
        responses = [
            response
            async for response in provider.text_chat_stream(
                prompt="hi",
                umo=UMO,
                conversation_id="cid-1",
                request_id="rid-1",
                model="gpt-4o",
            )
        ]
    finally:
        await provider.terminate()

    assert responses[-1].completion_text == "ok"
    assert _sent_headers(provider.custom_headers, captured[0]["extra_headers"]) == (
        _expected_headers()
    )


@pytest.mark.asyncio
async def test_openai_responses_sends_rendered_request_headers(monkeypatch):
    provider = ProviderOpenAIResponses(
        {
            "id": "provider-1",
            "type": "openai_responses",
            "model": "gpt-5",
            "key": ["test-key"],
            "custom_headers": dict(CUSTOM_HEADERS),
        },
        {},
    )
    captured: list[dict] = []

    async def fake_create(**kwargs):
        captured.append(kwargs)
        return OpenAIResponse.model_validate(
            {
                "id": "resp-1",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "gpt-5",
                "parallel_tool_calls": False,
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
        )

    monkeypatch.setattr(provider.client.responses, "create", fake_create)
    try:
        response = await provider.text_chat(
            prompt="hi",
            umo=UMO,
            conversation_id="cid-1",
            request_id="rid-1",
        )
    finally:
        await provider.terminate()

    assert response.completion_text == "ok"
    assert _sent_headers(provider.custom_headers, captured[0]["extra_headers"]) == (
        _expected_headers(model="gpt-5")
    )
    assert "x-session" not in provider.custom_headers


@pytest.mark.asyncio
async def test_openai_responses_stream_sends_rendered_request_headers(monkeypatch):
    provider = ProviderOpenAIResponses(
        {
            "id": "provider-1",
            "type": "openai_responses",
            "model": "gpt-5",
            "key": ["test-key"],
            "custom_headers": dict(CUSTOM_HEADERS),
        },
        {},
    )
    captured: list[dict] = []
    final_response = OpenAIResponse.model_validate(
        {
            "id": "resp-1",
            "object": "response",
            "created_at": 0,
            "status": "completed",
            "model": "gpt-5-mini",
            "parallel_tool_calls": False,
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
    )

    async def fake_stream():
        yield SimpleNamespace(
            type="response.created",
            response=SimpleNamespace(id="resp-1"),
        )
        yield SimpleNamespace(type="response.output_text.delta", delta="ok")
        yield SimpleNamespace(type="response.completed", response=final_response)

    async def fake_create(**kwargs):
        captured.append(kwargs)
        return fake_stream()

    monkeypatch.setattr(provider.client.responses, "create", fake_create)
    try:
        responses = [
            response
            async for response in provider.text_chat_stream(
                prompt="hi",
                umo=UMO,
                conversation_id="cid-1",
                request_id="rid-1",
                model="gpt-5-mini",
            )
        ]
    finally:
        await provider.terminate()

    assert responses[-1].completion_text == "ok"
    assert captured[0]["stream"] is True
    assert _sent_headers(provider.custom_headers, captured[0]["extra_headers"]) == (
        _expected_headers(model="gpt-5-mini")
    )


@pytest.mark.asyncio
async def test_openai_key_rotation_reuses_rendered_headers(monkeypatch):
    provider = ProviderOpenAIOfficial(
        {
            "id": "provider-1",
            "type": "openai_chat_completion",
            "model": "gpt-4o-mini",
            "key": ["key-a", "key-b"],
            "custom_headers": dict(CUSTOM_HEADERS),
        },
        {},
    )
    captured: list[tuple[str, dict]] = []

    async def fake_create(**kwargs):
        captured.append((provider.client.api_key, kwargs["extra_headers"]))
        if len(captured) == 1:
            raise Exception("429 too many requests, slow down")
        return _chat_completion()

    monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)
    try:
        response = await provider.text_chat(
            prompt="hi",
            umo=UMO,
            conversation_id="cid-1",
            request_id="rid-1",
        )
    finally:
        await provider.terminate()

    assert response.completion_text == "ok"
    assert len(captured) == 2
    assert captured[0][0] != captured[1][0]
    assert captured[0][1] == captured[1][1]
    assert _sent_headers(provider.custom_headers, captured[1][1]) == _expected_headers(
        model="gpt-4o-mini"
    )


@pytest.mark.asyncio
async def test_anthropic_text_chat_sends_rendered_request_headers(monkeypatch):
    provider = ProviderAnthropic(
        {
            "id": "provider-1",
            "type": "anthropic_chat_completion",
            "model": "claude-sonnet-4",
            "key": ["test-key"],
            "custom_headers": dict(CUSTOM_HEADERS),
        },
        {},
    )
    captured: list[dict] = []

    async def fake_create(**kwargs):
        captured.append(kwargs)
        return AnthropicMessage.model_validate(
            {
                "id": "msg-1",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )

    monkeypatch.setattr(provider.client.messages, "create", fake_create)
    try:
        response = await provider.text_chat(
            prompt="hi",
            umo=UMO,
            conversation_id="cid-1",
            request_id="rid-1",
        )
    finally:
        await provider.terminate()

    assert response.completion_text == "ok"
    assert _sent_headers(provider.custom_headers, captured[0]["extra_headers"]) == (
        _expected_headers(model="claude-sonnet-4")
    )
    assert "x-session" not in provider.custom_headers


@pytest.mark.asyncio
async def test_anthropic_text_chat_stream_forwards_rendered_headers(monkeypatch):
    provider = ProviderAnthropic(
        {
            "id": "provider-1",
            "type": "anthropic_chat_completion",
            "model": "claude-sonnet-4",
            "key": ["test-key"],
            "custom_headers": dict(CUSTOM_HEADERS),
        },
        {},
    )
    captured: list[dict] = []

    async def fake_query_stream(payloads, tools, **kwargs):
        captured.append(kwargs)
        yield LLMResponse(role="assistant", completion_text="ok")

    monkeypatch.setattr(provider, "_query_stream", fake_query_stream)
    try:
        responses = [
            response
            async for response in provider.text_chat_stream(
                prompt="hi",
                umo=UMO,
                conversation_id="cid-1",
                request_id="rid-1",
            )
        ]
    finally:
        await provider.terminate()

    assert responses[-1].completion_text == "ok"
    assert _sent_headers(provider.custom_headers, captured[0]["request_headers"]) == (
        _expected_headers(model="claude-sonnet-4")
    )


def _gemini_provider():
    return ProviderGoogleGenAI(
        {
            "id": "provider-1",
            "type": "googlegenai_chat_completion",
            "model": "gemini-2.5-flash",
            "api_base": "https://gemini.example.test",
            "key": ["test-key"],
            "custom_headers": dict(CUSTOM_HEADERS),
        },
        {},
    )


def _gemini_response(text="ok"):
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[genai_types.Part.from_text(text=text)]),
        finish_reason=genai_types.FinishReason.STOP,
    )
    return SimpleNamespace(
        candidates=[candidate], response_id="resp-1", usage_metadata=None
    )


@pytest.mark.asyncio
async def test_gemini_text_chat_sends_rendered_request_headers(monkeypatch):
    provider = _gemini_provider()
    captured: list[dict] = []

    async def fake_generate_content(**kwargs):
        captured.append(kwargs)
        return _gemini_response()

    monkeypatch.setattr(
        provider.client.models, "generate_content", fake_generate_content
    )
    try:
        response = await provider.text_chat(
            prompt="hi",
            umo=UMO,
            model="gemini-2.5-pro",
            conversation_id="cid-1",
            request_id="rid-1",
        )
        client_headers = dict(provider.client._api_client._http_options.headers)
    finally:
        await provider.terminate()

    assert response.completion_text == "ok"
    config = captured[0]["config"]
    assert config.http_options is not None
    expected = _expected_headers(model="gemini-2.5-pro")
    assert config.http_options.headers == {
        name: value
        for name, value in expected.items()
        if name not in {"x-provider", "x-version"}
    }
    sent = _sent_headers(client_headers, config.http_options.headers)
    for name, value in expected.items():
        assert sent[name] == value
    # The shared client keeps only static headers.
    assert "x-astrbot-conversation-id" not in client_headers
    assert "x-session" not in client_headers


@pytest.mark.asyncio
async def test_gemini_streams_do_not_block_each_other(monkeypatch):
    provider = _gemini_provider()
    entered: list[dict] = []
    release = asyncio.Event()

    async def fake_generate_stream(**kwargs):
        entered.append(kwargs["config"].http_options.headers)
        if len(entered) == 2:
            release.set()
        await asyncio.wait_for(release.wait(), timeout=5)

        async def generator():
            yield SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=SimpleNamespace(
                            parts=[genai_types.Part.from_text(text="ok")]
                        ),
                        finish_reason=genai_types.FinishReason.STOP,
                    )
                ],
                text="ok",
                response_id="resp-1",
                usage_metadata=None,
            )

        return generator()

    monkeypatch.setattr(
        provider.client.models, "generate_content_stream", fake_generate_stream
    )

    async def drain(conversation_id):
        return [
            response
            async for response in provider._query_stream(
                payloads={
                    "messages": [{"role": "user", "content": "hi"}],
                    "model": "gemini-2.5-flash",
                },
                tools=None,
                conversation_id=conversation_id,
                request_headers={
                    "x-astrbot-conversation-id": conversation_id,
                    "x-session": conversation_id,
                },
            )
        ]

    try:
        await asyncio.wait_for(
            asyncio.gather(drain("cid-1"), drain("cid-2")), timeout=10
        )
        client_headers = dict(provider.client._api_client._http_options.headers)
    finally:
        await provider.terminate()

    assert [headers["x-session"] for headers in entered] == ["cid-1", "cid-2"]
    assert "x-astrbot-conversation-id" not in client_headers
