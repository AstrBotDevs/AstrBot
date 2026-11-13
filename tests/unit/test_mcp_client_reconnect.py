from datetime import timedelta

import anyio
import httpx
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData
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
        (TimeoutError(), True),
        (
            McpError(
                ErrorData(
                    code=httpx.codes.REQUEST_TIMEOUT,
                    message="Timed out while waiting for response to ClientRequest. Waited 120.0 seconds.",
                )
            ),
            True,
        ),
        (
            McpError(ErrorData(code=httpx.codes.INTERNAL_SERVER_ERROR, message="boom")),
            False,
        ),
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


@pytest.mark.asyncio
async def test_call_tool_reconnects_on_read_timeout(monkeypatch) -> None:
    monkeypatch.setattr(mcp_client, "wait_exponential", lambda **_: wait_none())

    client = mcp_client.MCPClient()
    session = FlakyMcpSession(
        first_error=McpError(
            ErrorData(
                code=httpx.codes.REQUEST_TIMEOUT,
                message="Timed out while waiting for response to ClientRequest. Waited 120.0 seconds.",
            )
        )
    )
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

    assert result["name"] == "lookup"
    assert session.calls == 2
    assert reconnects == 1


@pytest.mark.asyncio
async def test_failed_reconnect_surfaces_original_error(monkeypatch) -> None:
    """A failing reconnect must not hide the original tool error.

    Regression test: when ``_reconnect()`` raises, the retry predicate must
    not see that exception; the caller should receive the original tool-call
    error instead of a bare ``ValueError`` about the missing session.
    """
    monkeypatch.setattr(mcp_client, "wait_exponential", lambda **_: wait_none())

    client = mcp_client.MCPClient()
    session = FlakyMcpSession()
    client.session = session

    async def failing_reconnect() -> None:
        client.session = None
        raise RuntimeError("reconnect transport blew up")

    client._reconnect = failing_reconnect

    with pytest.raises(RuntimeError, match="Session terminated"):
        await client.call_tool_with_reconnect(
            tool_name="lookup",
            arguments={"url": "https://example.com"},
            read_timeout_seconds=timedelta(seconds=5),
        )

    assert session.calls == 1
