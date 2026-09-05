import asyncio
import inspect
import json

import httpx
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

import astrbot.core.provider.sources.request_retry as request_retry
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


def _make_provider(kind: str, transport: httpx.AsyncBaseTransport):
    http_client = httpx.AsyncClient(transport=transport)
    if kind == "anthropic":
        client = AsyncAnthropic(
            api_key="test-key",
            base_url="https://example.test",
            http_client=http_client,
        )
        provider = ProviderAnthropic.__new__(ProviderAnthropic)
        provider.client = client
        provider.provider_config = {}
        provider.thinking_config = {}
        return provider, client, http_client

    client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://example.test/v1",
        http_client=http_client,
    )
    provider_cls = (
        ProviderOpenAIResponses if kind == "responses" else ProviderOpenAIOfficial
    )
    provider = provider_cls.__new__(provider_cls)
    provider.client = client
    provider.provider_config = {}
    endpoint = (
        client.responses.create
        if kind == "responses"
        else client.chat.completions.create
    )
    provider.default_params = inspect.signature(endpoint).parameters.keys()
    return provider, client, http_client


async def _query(provider, kind: str, *, attempts: int):
    if kind == "anthropic":
        payload = {
            "model": "claude-test",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 1024,
        }
    elif kind == "responses":
        payload = {"model": "gpt-test", "input": "hello", "store": False}
    else:
        payload = {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
        }
    return await provider._query(payload, None, request_max_retries=attempts)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["openai", "responses", "anthropic"])
async def test_disabled_rate_limit_retries_send_one_sdk_request(kind, monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    calls = 0
    request_bodies: list[bytes] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        request_bodies.append(request.content)
        return httpx.Response(
            429,
            request=request,
            json={"error": {"type": "rate_limit_error", "message": "limited"}},
        )

    provider, client, http_client = _make_provider(kind, httpx.MockTransport(handler))
    token = request_retry.provider_retry_rate_limits.set(False)
    try:
        with pytest.raises(Exception) as caught:
            await _query(provider, kind, attempts=5)
    finally:
        request_retry.provider_retry_rate_limits.reset(token)
        await http_client.aclose()

    assert getattr(caught.value, "status_code", None) == 429
    assert calls == 1
    assert client.max_retries == 2
    assert all(b"retry_rate_limits" not in body for body in request_bodies)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["openai", "responses", "anthropic"])
async def test_disabled_rate_limit_retries_send_one_stream_sdk_request(
    kind, monkeypatch
):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            request=request,
            json={"error": {"type": "rate_limit_error", "message": "limited"}},
        )

    provider, client, http_client = _make_provider(kind, httpx.MockTransport(handler))
    if kind == "anthropic":
        payload = {
            "model": "claude-test",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 1024,
        }
    elif kind == "responses":
        payload = {"model": "gpt-test", "input": "hello", "store": False}
    else:
        payload = {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
        }

    token = request_retry.provider_retry_rate_limits.set(False)
    stream = provider._query_stream(payload, None, request_max_retries=5)
    try:
        with pytest.raises(Exception) as caught:
            await anext(stream)
    finally:
        await stream.aclose()
        request_retry.provider_retry_rate_limits.reset(token)
        await http_client.aclose()

    assert getattr(caught.value, "status_code", None) == 429
    assert calls == 1
    assert client.max_retries == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["openai", "responses", "anthropic"])
@pytest.mark.parametrize("failure", ["server", "connection"])
async def test_disabled_rate_limit_retries_keep_outer_transient_retries(
    kind, failure, monkeypatch
):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if failure == "connection":
            raise httpx.ConnectError("temporary connection failure", request=request)
        return httpx.Response(
            500,
            request=request,
            json={"error": {"type": "api_error", "message": "temporary failure"}},
        )

    provider, client, http_client = _make_provider(kind, httpx.MockTransport(handler))
    token = request_retry.provider_retry_rate_limits.set(False)
    try:
        with pytest.raises(Exception):
            await _query(provider, kind, attempts=2)
    finally:
        request_retry.provider_retry_rate_limits.reset(token)
        await http_client.aclose()

    assert calls == (client.max_retries + 1) * 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["openai", "responses", "anthropic"])
async def test_default_rate_limit_policy_preserves_sdk_retries(kind, monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            request=request,
            json={"error": {"type": "rate_limit_error", "message": "limited"}},
        )

    provider, client, http_client = _make_provider(kind, httpx.MockTransport(handler))
    try:
        with pytest.raises(Exception):
            await _query(provider, kind, attempts=1)
    finally:
        await http_client.aclose()

    assert calls == client.max_retries + 1


@pytest.mark.asyncio
async def test_concurrent_rate_limit_policies_do_not_modify_shared_openai_client(
    monkeypatch,
):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    calls = {"gpt-disabled": 0, "gpt-default": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        calls[model] += 1
        return httpx.Response(
            429,
            request=request,
            json={"error": {"type": "rate_limit_error", "message": "limited"}},
        )

    provider, client, http_client = _make_provider(
        "openai", httpx.MockTransport(handler)
    )

    async def run(model: str, retry_rate_limits: bool) -> None:
        token = request_retry.provider_retry_rate_limits.set(retry_rate_limits)
        try:
            with pytest.raises(Exception):
                await provider._query(
                    {
                        "model": model,
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                    None,
                    request_max_retries=1,
                )
        finally:
            request_retry.provider_retry_rate_limits.reset(token)

    try:
        await asyncio.gather(
            run("gpt-disabled", False),
            run("gpt-default", True),
        )
    finally:
        await http_client.aclose()

    assert calls == {
        "gpt-disabled": 1,
        "gpt-default": client.max_retries + 1,
    }
    assert client.max_retries == 2


@pytest.mark.asyncio
async def test_openai_key_rotation_uses_structured_429_and_respects_policy():
    class StructuredRateLimitError(Exception):
        status_code = 429

    provider = ProviderOpenAIOfficial.__new__(ProviderOpenAIOfficial)
    error = StructuredRateLimitError("limited without status in message")
    available_keys = ["first-key", "second-key"]
    token = request_retry.provider_retry_rate_limits.set(False)
    try:
        with pytest.raises(StructuredRateLimitError) as caught:
            await provider._handle_api_error(
                error,
                {},
                [],
                None,
                available_keys[0],
                available_keys,
                0,
                10,
            )
    finally:
        request_retry.provider_retry_rate_limits.reset(token)

    assert caught.value is error
    assert available_keys == ["first-key", "second-key"]
