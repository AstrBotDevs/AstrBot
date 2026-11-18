import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import anyio
import pytest
from mcp import ClientSession

from astrbot.core.agent.mcp_client import MCPClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "session_created", [False, True], ids=["transport", "handshake"]
)
async def test_next_tool_call_recovers_after_failed_reconnect(
    monkeypatch, session_created
):
    client = MCPClient()
    closed = AsyncMock(spec=ClientSession)
    closed.call_tool.side_effect = anyio.ClosedResourceError
    recovered = AsyncMock(spec=ClientSession)
    attempts = iter([closed, None, recovered])

    async def connect(config, name):
        session = next(attempts)
        if session is None:
            if session_created:
                client.session = AsyncMock(spec=ClientSession)
            raise ConnectionError("MCP unavailable")
        client.session = session

    monkeypatch.setattr(client, "_do_connect", connect)
    await client.connect_to_server({"url": "http://example.invalid"}, "demo")
    try:
        timeout = timedelta(seconds=1)
        with pytest.raises(ConnectionError, match="MCP unavailable"):
            await client.call_tool_with_reconnect("lookup", {}, timeout)

        result = await client.call_tool_with_reconnect("lookup", {"id": 1}, timeout)
        assert result is recovered.call_tool.return_value
        recovered.call_tool.assert_awaited_once_with(
            name="lookup", arguments={"id": 1}, read_timeout_seconds=timeout
        )
    finally:
        await client.cleanup()


@pytest.mark.asyncio
async def test_concurrent_calls_on_same_closed_session_reconnect_once(monkeypatch):
    client = MCPClient()
    client._mcp_server_config = {"url": "http://example.invalid"}
    client._server_name = "demo"

    async def fail_call(**kwargs):
        # Let both callers start on the same session before reporting closure.
        await asyncio.sleep(0)
        raise anyio.ClosedResourceError

    closed = AsyncMock(spec=ClientSession)
    closed.call_tool.side_effect = fail_call
    client.session = closed

    recovered = AsyncMock(spec=ClientSession)
    recovered.call_tool.side_effect = lambda **kwargs: kwargs["arguments"]["id"]

    async def connect(config, name):
        client.session = recovered

    connect_mock = AsyncMock(side_effect=connect)
    monkeypatch.setattr(client, "_do_connect", connect_mock)
    try:
        results = await asyncio.gather(
            *(
                client.call_tool_with_reconnect(
                    "lookup", {"id": i}, timedelta(seconds=1)
                )
                for i in (1, 2)
            )
        )
        assert results == [1, 2]
        assert closed.call_tool.await_count == 2
        connect_mock.assert_awaited_once()
    finally:
        await client.cleanup()
