"""Retry the real request boundary without clocks or external services."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

import astrbot.core.provider.sources.request_retry as request_retry
from astrbot.core.provider.sources.request_retry import (
    retry_provider_request,
    retry_provider_request_context,
)


@pytest.fixture(autouse=True)
def immediate_retry_waits(monkeypatch, caplog):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)
    logger = logging.getLogger("astrbot")
    added = caplog.handler not in logger.handlers
    if added:
        logger.addHandler(caplog.handler)
    try:
        yield
    finally:
        if added:
            logger.removeHandler(caplog.handler)


@pytest.mark.asyncio
@pytest.mark.parametrize("attempts", [1, 2, 4])
async def test_retry_provider_request_uses_configured_max_retries(attempts, caplog):
    caplog.set_level(logging.WARNING, logger="astrbot")
    error = httpx.ConnectError("temporary connection failure")
    request = AsyncMock(side_effect=error)

    with pytest.raises(httpx.ConnectError) as raised:
        await retry_provider_request("Test", request, max_attempts=attempts)

    assert raised.value is error
    assert request.await_count == attempts
    if attempts > 1:
        assert "temporary connection failure" in caplog.text


@pytest.mark.asyncio
async def test_retry_returns_first_success_without_an_extra_request():
    result = object()
    request = AsyncMock(side_effect=[httpx.ConnectError("offline"), result])

    assert await retry_provider_request("Test", request, max_attempts=4) is result
    assert request.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "retry_rate_limits", "attempts"),
    [
        (400, True, 1),
        (401, True, 1),
        (403, True, 1),
        (404, True, 1),
        (408, True, 3),
        (409, True, 3),
        (429, True, 3),
        (429, False, 1),
        (500, True, 3),
        (501, True, 3),
        (503, True, 3),
        (529, True, 3),
    ],
)
async def test_http_status_controls_retry_budget(status, retry_rate_limits, attempts):
    response = httpx.Response(
        status, request=httpx.Request("POST", "https://provider.invalid/test")
    )
    error = httpx.HTTPStatusError(
        "request failed", request=response.request, response=response
    )
    request = AsyncMock(side_effect=error)

    with pytest.raises(httpx.HTTPStatusError) as raised:
        await retry_provider_request(
            "Test", request, max_attempts=3, retry_rate_limits=retry_rate_limits
        )

    assert raised.value is error
    assert request.await_count == attempts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [ValueError("invalid input"), asyncio.CancelledError()]
)
async def test_validation_and_cancellation_are_never_retried(error):
    request = AsyncMock(side_effect=error)

    with pytest.raises(type(error)) as raised:
        await retry_provider_request("Test", request, max_attempts=4)

    assert raised.value is error
    request.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_private_error_details_can_be_omitted_from_retry_logs(caplog):
    caplog.set_level(logging.WARNING, logger="astrbot")
    request = AsyncMock(side_effect=httpx.ConnectError("private-prompt-and-key"))

    with pytest.raises(httpx.ConnectError):
        await retry_provider_request(
            "Test", request, max_attempts=2, log_error_details=False
        )

    assert request.await_count == 2
    assert "ConnectError" in caplog.text
    assert "private-prompt-and-key" not in caplog.text


@pytest.mark.asyncio
async def test_context_retries_entry_then_closes_only_the_acquired_context():
    failed = SimpleNamespace(
        __aenter__=AsyncMock(side_effect=httpx.ConnectError("offline")),
        __aexit__=AsyncMock(return_value=False),
    )
    value = object()
    acquired = SimpleNamespace(
        __aenter__=AsyncMock(return_value=value),
        __aexit__=AsyncMock(return_value=False),
    )
    factory = Mock(side_effect=[failed, acquired])

    async with retry_provider_request_context(
        "Test", factory, max_attempts=3
    ) as result:
        assert result is value

    assert factory.call_count == 2
    failed.__aexit__.assert_not_awaited()
    acquired.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [httpx.ConnectError("stream failed"), asyncio.CancelledError()]
)
async def test_context_body_errors_close_the_stream_without_replaying_it(error):
    acquired = SimpleNamespace(
        __aenter__=AsyncMock(return_value="stream"),
        __aexit__=AsyncMock(return_value=False),
    )
    factory = Mock(return_value=acquired)

    with pytest.raises(type(error)) as raised:
        async with retry_provider_request_context("Test", factory, max_attempts=3):
            raise error

    assert raised.value is error
    factory.assert_called_once_with()
    acquired.__aexit__.assert_awaited_once()
    exit_type, exit_error, exit_traceback = acquired.__aexit__.await_args.args
    assert exit_type is type(error)
    assert exit_error is error
    assert exit_traceback is not None
