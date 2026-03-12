from __future__ import annotations

import pytest

from astrbot.core.agent.mcp_client import MCPClient
from astrbot.core.agent.mcp_stdio_client import _should_ignore_stdout_line


class _DummyAsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _RecordingClientSession:
    constructor_calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        self.__class__.constructor_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def initialize(self):
        return None


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "> mcp-minimal-server@1.0.0 start:stdio",
        "> node stdio.js",
        "npm notice",
    ],
)
def test_should_ignore_non_protocol_stdio_stdout_lines(line: str):
    assert _should_ignore_stdout_line(line) is True


@pytest.mark.parametrize(
    "line",
    [
        '{"jsonrpc":"2.0","id":1,"result":{}}',
        '{"jsonrpc":"2.0","method":"notifications/message","params":{"level":"info"}}',
        "{not-valid-json-yet}",
    ],
)
def test_should_keep_json_like_stdio_stdout_lines_for_protocol_parsing(line: str):
    assert _should_ignore_stdout_line(line) is False


@pytest.mark.asyncio
async def test_mcp_client_stdio_path_uses_tolerant_transport(
    monkeypatch: pytest.MonkeyPatch,
):
    _RecordingClientSession.constructor_calls.clear()
    transport_calls: list[dict] = []

    def _fake_tolerant_stdio_client(server_params, errlog):
        transport_calls.append(
            {
                "server_params": server_params,
                "errlog": errlog,
            }
        )
        return _DummyAsyncContext(("read", "write"))

    monkeypatch.setattr(
        "astrbot.core.agent.mcp_client.tolerant_stdio_client",
        _fake_tolerant_stdio_client,
    )
    monkeypatch.setattr(
        "astrbot.core.agent.mcp_client.mcp.ClientSession",
        _RecordingClientSession,
    )

    client = MCPClient()
    await client.connect_to_server(
        {
            "command": "node",
            "args": ["stdio.js"],
        },
        "demo",
    )

    assert len(transport_calls) == 1
    server_params = transport_calls[0]["server_params"]
    assert server_params.command == "node"
    assert server_params.args == ["stdio.js"]
    assert _RecordingClientSession.constructor_calls

    await client.cleanup()
