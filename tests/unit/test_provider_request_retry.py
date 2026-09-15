import pytest

from astrbot.core.exceptions import ProviderRequestTooLargeError
from astrbot.core.provider.sources.request_retry import retry_provider_request


class _Response:
    status_code = 413


class _RequestTooLargeError(Exception):
    response = _Response()


@pytest.mark.asyncio
async def test_memory_error_is_not_retried():
    calls = 0

    async def request():
        nonlocal calls
        calls += 1
        raise MemoryError("allocation failed")

    with pytest.raises(MemoryError):
        await retry_provider_request("test", request, max_attempts=5)
    assert calls == 1


@pytest.mark.asyncio
async def test_http_413_becomes_typed_request_size_error_without_retry():
    calls = 0

    async def request():
        nonlocal calls
        calls += 1
        raise _RequestTooLargeError("payload too large")

    with pytest.raises(ProviderRequestTooLargeError, match="HTTP 413"):
        await retry_provider_request("test", request, max_attempts=5)
    assert calls == 1
