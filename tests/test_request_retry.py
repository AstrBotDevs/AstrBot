import httpx
import pytest

import astrbot.core.provider.sources.request_retry as request_retry
from astrbot.core.provider.sources.request_retry import retry_provider_request


@pytest.mark.asyncio
async def test_retry_provider_request_logs_provider_id_and_model(
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)

    async def request():
        raise httpx.ConnectError("temporary connection failure")

    with caplog.at_level("WARNING", logger="astrbot"):
        with pytest.raises(httpx.ConnectError):
            await retry_provider_request(
                "OpenAI",
                request,
                provider_id="openai-main",
                model="gpt-4o-mini",
                max_attempts=2,
            )

    assert any(
        "[OpenAI] (provider_id=openai-main, model=gpt-4o-mini) Request failed"
        in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_retry_provider_request_preserves_existing_log_without_metadata(
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)

    async def request():
        raise httpx.ConnectError("temporary connection failure")

    with caplog.at_level("WARNING", logger="astrbot"):
        with pytest.raises(httpx.ConnectError):
            await retry_provider_request("OpenAI", request, max_attempts=2)

    assert any("[OpenAI] Request failed" in record.message for record in caplog.records)


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
