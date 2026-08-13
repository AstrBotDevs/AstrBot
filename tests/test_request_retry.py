import logging

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
async def test_retry_log_includes_provider_id_and_model(monkeypatch, caplog):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)

    async def request():
        raise httpx.ConnectError("temporary connection failure")

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        with pytest.raises(httpx.ConnectError):
            await retry_provider_request(
                "OpenAI",
                request,
                max_attempts=2,
                provider_id="my-openai-instance",
                model="gpt-4o",
            )

    assert "[OpenAI]" in caplog.text
    assert "provider=my-openai-instance" in caplog.text
    assert "model=gpt-4o" in caplog.text


@pytest.mark.asyncio
async def test_retry_log_omits_details_when_not_provided(monkeypatch, caplog):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)

    async def request():
        raise httpx.ConnectError("temporary connection failure")

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        with pytest.raises(httpx.ConnectError):
            await retry_provider_request(
                "OpenAI",
                request,
                max_attempts=2,
            )

    assert "[OpenAI] Request failed with retryable error" in caplog.text
    assert "provider=" not in caplog.text
    assert "model=" not in caplog.text
