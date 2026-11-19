"""Offline regression for streaming key-rotation success at the final attempt.

Uses the real provider, OpenAI SDK and SSE parser. Only HTTP I/O and backoff
sleep are replaced. Test data is synthetic; no external API is contacted.
"""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import AsyncOpenAI, BadRequestError, RateLimitError

import astrbot.core.provider.sources.openai_source as source
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


@pytest.mark.asyncio
@pytest.mark.parametrize("success_attempt", [1, 9, 10, None])
@pytest.mark.parametrize("stream", [True, False])
async def test_final_rotation_success(monkeypatch, success_attempt, stream):
    provider = ProviderOpenAIOfficial(
        provider_config={
            "id": "offline-retry-test",
            "type": "openai_chat_completion",
            "model": "test-model",
            "key": [f"synthetic-test-key-{index}" for index in range(11)],
        },
        provider_settings={},
    )
    await provider.client.close()
    requests = []

    async def respond(request):
        requests.append(request)
        if success_attempt is None or len(requests) < success_attempt:
            return httpx.Response(
                429,
                json={
                    "error": {"message": "test rate limit", "type": "rate_limit_error"}
                },
            )
        if not stream:
            return httpx.Response(
                200,
                json={
                    "id": "offline-completion",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "test-model",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "complete"},
                        }
                    ],
                },
            )
        chunk = {
            "id": "offline-completion",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "delta": {"role": "assistant", "content": "complete"},
                }
            ],
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode(),
        )

    provider.client = AsyncOpenAI(
        api_key="synthetic-unused-key",
        base_url="https://offline.invalid/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    monkeypatch.setattr(source.asyncio, "sleep", AsyncMock())
    responses = []
    error = None
    try:
        if stream:
            async for response in provider.text_chat_stream(
                prompt="hello", request_max_retries=1
            ):
                responses.append((response.is_chunk, response.completion_text))
        else:
            response = await provider.text_chat(prompt="hello", request_max_retries=1)
            responses.append((False, response.completion_text))
    except Exception as exc:
        error = exc
    finally:
        await provider.terminate()

    expected_attempts = success_attempt or 10
    assert len(requests) == expected_attempts
    assert (
        len({request.headers["authorization"] for request in requests})
        == expected_attempts
    )
    if success_attempt is None:
        assert isinstance(error, RateLimitError)
        assert not responses
    else:
        assert responses[-1] == (False, "complete")
        assert error is None, (
            f"successful attempt {success_attempt} yielded {responses}, then raised {error!r}"
        )


@pytest.mark.asyncio
async def test_stream_nonretryable_error_remains_visible(monkeypatch):
    provider = ProviderOpenAIOfficial(
        provider_config={
            "id": "offline",
            "type": "openai_chat_completion",
            "model": "test-model",
            "key": ["synthetic-key"],
        },
        provider_settings={},
    )
    await provider.client.close()
    calls = 0

    async def respond(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            400,
            json={
                "error": {"message": "invalid request", "type": "invalid_request_error"}
            },
        )

    provider.client = AsyncOpenAI(
        api_key="synthetic-key",
        base_url="https://offline.invalid/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    try:
        with pytest.raises(BadRequestError):
            _ = [
                response
                async for response in provider.text_chat_stream(
                    prompt="hello", request_max_retries=1
                )
            ]
        assert calls == 1
    finally:
        await provider.terminate()
