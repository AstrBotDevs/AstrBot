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
async def test_retry_provider_request_does_not_retry_invalid_request_body(monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    calls = 0

    class InvalidRequestError(Exception):
        status_code = 500
        body = {"error": {"code": "invalid_request"}}

    async def request():
        nonlocal calls
        calls += 1
        raise InvalidRequestError("proxy request validation failed")

    with pytest.raises(InvalidRequestError):
        await retry_provider_request("Test", request, max_attempts=5)

    assert calls == 1
