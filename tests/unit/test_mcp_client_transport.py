import asyncio
import inspect
import json
from contextlib import AsyncExitStack
from unittest.mock import AsyncMock

import httpx
import pytest

from astrbot.core.agent import mcp_client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transport", "sdk_version", "follow_redirects"),
    [
        ("sse", "1.29.0", True),
        ("sse", "1.30.0", False),
        ("streamable_http", "1.29.0", True),
        ("streamable_http", "1.30.0", False),
    ],
)
async def test_sdk_transport_uses_shared_tls_and_preserves_redirect_behavior(
    monkeypatch, transport, sdk_version, follow_redirects
):
    class StopBeforeConnecting(Exception):
        pass

    def transport_factory(*, httpx_client_factory, **kwargs):
        assert httpx_client_factory.keywords == {
            "verify": verify,
            "follow_redirects": follow_redirects,
        }
        assert kwargs["headers"] == headers
        raise StopBeforeConnecting

    headers = {"Authorization": "Bearer example"}
    verify = mcp_client.get_httpx_default_verify()
    monkeypatch.setattr(mcp_client, "version", lambda _: sdk_version)
    monkeypatch.setattr(
        mcp_client, "_quick_test_mcp_connection", AsyncMock(return_value=(True, ""))
    )
    monkeypatch.setattr(mcp_client, "sse_client", transport_factory)
    monkeypatch.setattr(mcp_client, "streamable_http_client_legacy", transport_factory)

    client = mcp_client.MCPClient()
    async with AsyncExitStack() as client.exit_stack:
        with pytest.raises(StopBeforeConnecting):
            await client._do_connect(
                {
                    "url": "https://mcp.example",
                    "transport": transport,
                    "headers": headers,
                },
                "example",
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["sse", "streamable_http"])
async def test_real_sdk_transport_creates_and_closes_httpx_client(
    monkeypatch, transport
):
    sdk_transport = (
        mcp_client.sse_client
        if transport == "sse"
        else mcp_client.streamable_http_client_legacy
    )
    if (
        sdk_transport is None
        or "httpx_client_factory" not in inspect.signature(sdk_transport).parameters
    ):
        pytest.skip("Installed MCP transport does not support client factory injection")

    sse_message = asyncio.get_running_loop().create_future()
    headers = {"Authorization": "Bearer example"}
    verify = mcp_client.get_httpx_default_verify()
    clients = []

    class EventStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"event: endpoint\ndata: /messages\n\n"
            yield b"event: message\ndata: " + await sse_message + b"\n\n"
            # Keep the event stream open until the SDK closes it.
            await asyncio.Event().wait()

    def handle_request(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == headers["Authorization"]
        if request.method == "GET":
            if transport == "sse":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/event-stream"},
                    stream=EventStream(),
                )
            return httpx.Response(405)

        assert request.method == "POST"
        message = json.loads(request.content)
        if message["method"] == "notifications/initialized":
            return httpx.Response(202)
        assert message["method"] == "initialize"
        response = {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {},
                "serverInfo": {"name": "test-server", "version": "1.0"},
            },
        }
        if transport == "sse":
            sse_message.set_result(json.dumps(response).encode())
            return httpx.Response(202)
        return httpx.Response(200, json=response)

    class RecordingClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            assert kwargs["verify"] is verify
            assert kwargs["auth"] is None
            super().__init__(transport=httpx.MockTransport(handle_request), **kwargs)
            clients.append(self)

    monkeypatch.setattr(httpx, "AsyncClient", RecordingClient)
    monkeypatch.setattr(
        mcp_client, "_quick_test_mcp_connection", AsyncMock(return_value=(True, ""))
    )
    client = mcp_client.MCPClient()
    async with asyncio.timeout(5), AsyncExitStack() as client.exit_stack:
        await client._do_connect(
            {
                "url": "https://mcp.example/",
                "transport": transport,
                "headers": headers,
                "timeout": 7,
                "sse_read_timeout": 19,
            },
            "example",
        )
        assert len(clients) == 1
        assert clients[0].timeout.connect == 7
        assert clients[0].timeout.read == 19
        assert not clients[0].is_closed
    assert clients[0].is_closed
