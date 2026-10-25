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
async def test_retry_provider_request_can_disable_only_rate_limit_retries(monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    attempts = 0

    class RateLimitedConnectionError(ConnectionError):
        status_code = 429

    async def request():
        nonlocal attempts
        attempts += 1
        raise RateLimitedConnectionError("rate limited")

    with pytest.raises(RateLimitedConnectionError):
        await retry_provider_request(
            "test-provider",
            request,
            retry_rate_limits=False,
            max_attempts=3,
        )

    assert attempts == 1


@pytest.mark.asyncio
async def test_retry_provider_request_keeps_other_network_retries(monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    attempts = 0

    async def request():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("temporary network failure")
        return "ok"

    result = await retry_provider_request(
        "test-provider",
        request,
        retry_rate_limits=False,
        max_attempts=3,
    )

    assert result == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_http_status_error_429_is_not_misclassified_as_connection_retry(
    monkeypatch,
):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    attempts = 0
    request_obj = httpx.Request("POST", "https://example.test")
    response = httpx.Response(429, request=request_obj)

    async def request():
        nonlocal attempts
        attempts += 1
        raise httpx.HTTPStatusError(
            "rate limited",
            request=request_obj,
            response=response,
        )

    with pytest.raises(httpx.HTTPStatusError):
        await retry_provider_request(
            "test-provider",
            request,
            retry_rate_limits=False,
            max_attempts=3,
        )

    assert attempts == 1
