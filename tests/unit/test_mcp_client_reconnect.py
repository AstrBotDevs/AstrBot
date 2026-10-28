from datetime import timedelta

import anyio
import pytest
from tenacity import wait_none

from astrbot.core.agent import mcp_client


class FlakyMcpSession:
    def __init__(self, first_error: Exception | None = None) -> None:
        self.calls = 0
        self.first_error = first_error or RuntimeError("Session terminated")

    async def call_tool(
        self,
        *,
        name: str,
        arguments: dict,
        read_timeout_seconds: timedelta,
    ) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            raise self.first_error
        return {
            "name": name,
            "arguments": arguments,
            "timeout": read_timeout_seconds.total_seconds(),
        }


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RuntimeError("Session terminated"), True),
        (RuntimeError("SESSION TERMINATED"), True),
        (RuntimeError("session was terminated"), True),
        (anyio.ClosedResourceError(), True),
        (RuntimeError("business flow terminated normally"), False),
        (RuntimeError("terminated"), False),
    ],
)
def test_mcp_reconnect_error_detection_is_narrow(
    error: BaseException, expected: bool
) -> None:
    assert mcp_client._is_mcp_reconnect_error(error) is expected


@pytest.mark.asyncio
async def test_call_tool_reconnects_on_session_terminated(monkeypatch) -> None:
    monkeypatch.setattr(mcp_client, "wait_exponential", lambda **_: wait_none())

    client = mcp_client.MCPClient()
    session = FlakyMcpSession()
    reconnects = 0

    async def reconnect() -> None:
        nonlocal reconnects
        reconnects += 1
        client.session = session

    client.session = session
    client._reconnect = reconnect

    result = await client.call_tool_with_reconnect(
        tool_name="lookup",
        arguments={"url": "https://example.com"},
        read_timeout_seconds=timedelta(seconds=5),
    )

    assert result == {
        "name": "lookup",
        "arguments": {"url": "https://example.com"},
        "timeout": 5.0,
    }
    assert session.calls == 2
    assert reconnects == 1


@pytest.mark.asyncio
async def test_call_tool_does_not_reconnect_on_business_error(monkeypatch) -> None:
    monkeypatch.setattr(mcp_client, "wait_exponential", lambda **_: wait_none())

    client = mcp_client.MCPClient()
    session = FlakyMcpSession(first_error=ValueError("business logic failed"))
    reconnects = 0

    async def reconnect() -> None:
        nonlocal reconnects
        reconnects += 1

    client.session = session
    client._reconnect = reconnect

    with pytest.raises(ValueError, match="business logic failed"):
        await client.call_tool_with_reconnect(
            tool_name="lookup",
            arguments={"url": "https://example.com"},
            read_timeout_seconds=timedelta(seconds=5),
        )

    assert session.calls == 1
    assert reconnects == 0
