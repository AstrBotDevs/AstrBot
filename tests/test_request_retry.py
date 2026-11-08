import httpx
import pytest

import astrbot.core.provider.sources.request_retry as request_retry
from astrbot.core.provider.sources.request_retry import retry_provider_request


@pytest.mark.asyncio
async def test_retry_provider_request_uses_configured_max_retries(monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)

    calls = 0

    async def request():
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("temporary connection failure")

    with pytest.raises(httpx.ConnectError):
        await retry_provider_request(
            "Test",
            request,
            max_attempts=2,
        )

    assert calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize(
    "error_type", [httpx.UnsupportedProtocol, httpx.LocalProtocolError]
)
async def test_local_protocol_errors_are_not_retried(monkeypatch, wrapped, error_type):
    from openai import APIConnectionError

    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    request = httpx.Request("POST", "https://example.invalid/v1")
    error = error_type("invalid local HTTP configuration", request=request)
    if wrapped:
        wrapper = APIConnectionError(request=request)
        wrapper.__cause__ = error
        error = wrapper
    calls = 0

    async def send():
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(type(error)) as caught:
        await retry_provider_request("Test", send, max_attempts=3)
    assert caught.value is error
    assert calls == 1


@pytest.mark.asyncio
async def test_real_sdk_unsupported_base_url_fails_after_one_attempt(monkeypatch):
    from openai import AsyncOpenAI

    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    attempts = 0
    async with httpx.AsyncClient(trust_env=False) as http_client:
        async with AsyncOpenAI(
            api_key="synthetic-test-key",
            base_url="ftp://example.invalid/v1",
            max_retries=0,
            http_client=http_client,
        ) as client:

            async def send():
                nonlocal attempts
                attempts += 1
                return await client.chat.completions.create(
                    model="test", messages=[{"role": "user", "content": "hello"}]
                )

            with pytest.raises(Exception) as caught:
                await retry_provider_request("Test", send, max_attempts=3)
    assert type(caught.value).__name__ == "APIConnectionError"
    assert isinstance(caught.value.__cause__, httpx.UnsupportedProtocol)
    assert attempts == 1


@pytest.mark.parametrize(
    "error_type",
    [
        httpx.ConnectError,
        httpx.ReadTimeout,
        httpx.RemoteProtocolError,
        httpx.ProxyError,
    ],
)
def test_transient_transport_errors_remain_retryable(error_type):
    from openai import APIConnectionError

    request = httpx.Request("POST", "https://example.invalid/v1")
    error = error_type("temporary transport failure", request=request)
    wrapper = APIConnectionError(request=request)
    wrapper.__cause__ = error
    for candidate in (error, wrapper):
        assert request_retry._is_retryable_provider_request_error(
            candidate,
            retry_rate_limits=True,
        )


def test_ambiguous_sdk_connection_error_remains_retryable():
    from openai import APIConnectionError

    request = httpx.Request("POST", "https://example.invalid/v1")
    for cause in (None, RuntimeError("unknown transport failure")):
        error = APIConnectionError(request=request)
        error.__cause__ = cause
        assert request_retry._is_retryable_provider_request_error(
            error,
            retry_rate_limits=True,
        )


@pytest.mark.asyncio
async def test_stream_context_does_not_retry_local_protocol_error(monkeypatch):
    from contextlib import asynccontextmanager

    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    attempts = 0

    @asynccontextmanager
    async def stream():
        nonlocal attempts
        attempts += 1
        raise httpx.UnsupportedProtocol("unsupported URL scheme")
        yield

    with pytest.raises(httpx.UnsupportedProtocol):
        async with request_retry.retry_provider_request_context(
            "Test", stream, max_attempts=3
        ):
            pytest.fail("The context must not be entered")
    assert attempts == 1


@pytest.mark.asyncio
async def test_wrapped_remote_protocol_error_retries_until_success(monkeypatch):
    from openai import APIConnectionError

    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    request = httpx.Request("POST", "https://example.invalid/v1")
    calls = 0

    async def send():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise APIConnectionError(request=request) from httpx.RemoteProtocolError(
                "Server disconnected without sending a response", request=request
            )
        return "completed"

    assert await retry_provider_request("Test", send, max_attempts=3) == "completed"
    assert calls == 2
