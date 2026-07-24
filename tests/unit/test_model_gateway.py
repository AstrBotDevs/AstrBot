import asyncio

import pytest

from astrbot.core.agent.model_gateway import ModelErrorCode, ModelGateway


@pytest.mark.asyncio
async def test_model_gateway_bounds_request_timeout() -> None:
    async def request():
        await asyncio.sleep(1)

    outcome = await ModelGateway.complete(request, timeout=0.01, provider_id="test")

    assert outcome.status == "failed"
    assert outcome.error_code == ModelErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_model_gateway_stream_emits_terminal_event_once() -> None:
    async def request():
        yield "hello"

    events = [
        event
        async for event in ModelGateway.stream(request, timeout=1, provider_id="test")
    ]

    assert [event.kind for event in events] == ["START", "DELTA", "END"]


@pytest.mark.asyncio
async def test_model_gateway_classifies_rate_limit_without_retry() -> None:
    async def request():
        raise RuntimeError("HTTP 429 resource_exhausted")

    outcome = await ModelGateway.complete(request, timeout=1, provider_id="test")

    assert outcome.error_code == ModelErrorCode.RATE_LIMITED


@pytest.mark.asyncio
async def test_model_gateway_classifies_server_disconnect_as_network_error() -> None:
    async def request():
        raise RuntimeError("Server disconnected without sending a response")

    outcome = await ModelGateway.complete(request, timeout=1, provider_id="test")

    assert outcome.error_code == ModelErrorCode.NETWORK
