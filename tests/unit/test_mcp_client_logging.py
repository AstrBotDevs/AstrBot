from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import mcp
import pytest

from astrbot.core.agent.mcp_client import MCPClient


@pytest.mark.asyncio
async def test_stdio_session_uses_bounded_async_protocol_logging_callback():
    session = AsyncMock()
    session.initialize.return_value = SimpleNamespace(capabilities=SimpleNamespace())
    client = MCPClient()
    client.exit_stack = SimpleNamespace(
        enter_async_context=AsyncMock(
            side_effect=[("read-stream", "write-stream"), session]
        )
    )

    with (
        patch(
            "astrbot.core.agent.mcp_client.mcp.stdio_client",
            return_value=MagicMock(),
        ),
        patch(
            "astrbot.core.agent.mcp_client.mcp.ClientSession",
            return_value=session,
        ) as session_factory,
        patch(
            "astrbot.core.agent.mcp_client.LogPipe",
            return_value=MagicMock(),
        ) as log_pipe_factory,
    ):
        await client._do_connect(
            {"command": "python", "args": []},
            "logging-server",
        )

    logging_callback = session_factory.call_args.kwargs["logging_callback"]
    assert "callback" not in log_pipe_factory.call_args.kwargs

    await logging_callback(
        mcp.types.LoggingMessageNotificationParams(level="info", data="ignored")
    )
    for index in range(101):
        await logging_callback(
            mcp.types.LoggingMessageNotificationParams(
                level="warning",
                data=f"log-{index}-" + "x" * 5000,
            )
        )

    assert len(client.server_errlogs) == 100
    assert client.server_errlogs[0].startswith("[WARNING] log-1-")
    assert client.server_errlogs[-1].startswith("[WARNING] log-100-")
    assert all(len(log) <= 4096 for log in client.server_errlogs)
    assert all(log.endswith("...") for log in client.server_errlogs)
