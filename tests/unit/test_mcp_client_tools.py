import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import mcp
import pytest

from astrbot.core.agent.mcp_client import MCPClient


def _page(tool_names, next_cursor=None):
    return SimpleNamespace(
        tools=[SimpleNamespace(name=name) for name in tool_names],
        nextCursor=next_cursor,
    )


def _client(session):
    client = MCPClient()
    client.session = session
    return client


class TestMCPToolPagination:
    @pytest.mark.asyncio
    async def test_first_page_failure_propagates_without_changing_tools(self):
        session = AsyncMock()
        session.list_tools.side_effect = RuntimeError("unavailable")
        client = _client(session)
        previous_tools = [SimpleNamespace(name="existing")]
        client.tools = previous_tools

        with pytest.raises(RuntimeError, match="unavailable"):
            await client.list_tools_and_save()

        assert client.tools is previous_tools
        session.list_tools.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_single_page_preserves_sdk_1_8_compatible_call(self):
        session = AsyncMock()
        first_page = _page(["alpha"])
        session.list_tools.return_value = first_page
        client = _client(session)

        result = await client.list_tools_and_save()

        assert result is first_page
        assert [tool.name for tool in client.tools] == ["alpha"]
        session.list_tools.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_all_pages_are_merged_in_order(self):
        session = AsyncMock()
        first_page = _page(["alpha"], "page-2")
        session.list_tools.side_effect = [
            first_page,
            _page(["beta"], "page-3"),
            _page(["gamma"]),
        ]
        client = _client(session)

        result = await client.list_tools_and_save()

        assert result is first_page
        assert result.nextCursor is None
        assert [tool.name for tool in result.tools] == ["alpha", "beta", "gamma"]
        assert client.tools is result.tools
        assert session.list_tools.await_args_list == [
            call(),
            call(cursor="page-2"),
            call(cursor="page-3"),
        ]

    @pytest.mark.asyncio
    async def test_params_api_is_preferred_when_available(self):
        first_page = _page(["alpha"], "page-2")
        second_page = _page(["beta"])

        class PaginatedRequestParams:
            def __init__(self, cursor):
                self.cursor = cursor

        class ParamsSession:
            def __init__(self):
                self.calls = []

            async def list_tools(self, cursor=None, *, params=None):
                self.calls.append((cursor, params))
                return first_page if len(self.calls) == 1 else second_page

        session = ParamsSession()
        client = _client(session)

        with patch.object(
            mcp.types,
            "PaginatedRequestParams",
            PaginatedRequestParams,
            create=True,
        ):
            result = await client.list_tools_and_save()

        assert [tool.name for tool in result.tools] == ["alpha", "beta"]
        assert session.calls[0] == (None, None)
        assert session.calls[1][0] is None
        assert session.calls[1][1].cursor == "page-2"

    @pytest.mark.asyncio
    async def test_empty_cursor_is_forwarded_as_opaque_value(self):
        session = AsyncMock()
        session.list_tools.side_effect = [
            _page(["alpha"], ""),
            _page(["beta"]),
        ]
        client = _client(session)

        result = await client.list_tools_and_save()

        assert [tool.name for tool in result.tools] == ["alpha", "beta"]
        assert session.list_tools.await_args_list == [call(), call(cursor="")]

    @pytest.mark.asyncio
    async def test_sdk_without_cursor_support_keeps_first_page(self):
        first_page = _page(["alpha"], "page-2")

        class MCP18Session:
            async def list_tools(self):
                return first_page

        client = _client(MCP18Session())

        with patch("astrbot.core.agent.mcp_client.logger.warning") as warning:
            result = await client.list_tools_and_save()

        assert result is first_page
        assert client.tools is first_page.tools
        warning.assert_called_once()
        assert "does not support pagination cursors" in warning.call_args.args[0]

    @pytest.mark.asyncio
    async def test_repeated_cursor_keeps_first_page(self):
        session = AsyncMock()
        first_page = _page(["alpha"], "repeat")
        session.list_tools.side_effect = [
            first_page,
            _page(["partial"], "repeat"),
        ]
        client = _client(session)

        with patch("astrbot.core.agent.mcp_client.logger.warning") as warning:
            result = await client.list_tools_and_save()

        assert result is first_page
        assert [tool.name for tool in client.tools] == ["alpha"]
        warning.assert_called_once()
        assert "repeated a pagination cursor" in warning.call_args.args[0]

    @pytest.mark.asyncio
    async def test_page_limit_keeps_first_page(self):
        session = AsyncMock()
        first_page = _page(["alpha"], "page-2")
        session.list_tools.side_effect = [
            first_page,
            _page(["partial"], "page-3"),
        ]
        client = _client(session)

        with (
            patch("astrbot.core.agent.mcp_client._MCP_TOOL_LIST_MAX_PAGES", 2),
            patch("astrbot.core.agent.mcp_client.logger.warning") as warning,
        ):
            result = await client.list_tools_and_save()

        assert result is first_page
        assert [tool.name for tool in client.tools] == ["alpha"]
        warning.assert_called_once()
        assert "exceeded 2 pages" in warning.call_args.args[0]
        assert session.list_tools.await_args_list == [call(), call(cursor="page-2")]

    @pytest.mark.asyncio
    async def test_later_page_failure_keeps_first_page(self):
        session = AsyncMock()
        first_page = _page(["alpha"], "page-2")
        session.list_tools.side_effect = [first_page, RuntimeError("unavailable")]
        client = _client(session)

        with patch("astrbot.core.agent.mcp_client.logger.warning") as warning:
            result = await client.list_tools_and_save()

        assert result is first_page
        assert [tool.name for tool in client.tools] == ["alpha"]
        warning.assert_called_once()
        warning_message = warning.call_args.args[0]
        assert "failed (RuntimeError)" in warning_message
        assert "unavailable" not in warning_message

    @pytest.mark.asyncio
    async def test_later_page_type_error_propagates_without_changing_tools(self):
        session = AsyncMock()
        session.list_tools.side_effect = [
            _page(["alpha"], "page-2"),
            TypeError("invalid response payload"),
        ]
        client = _client(session)
        previous_tools = [SimpleNamespace(name="existing")]
        client.tools = previous_tools

        with pytest.raises(TypeError, match="invalid response payload"):
            await client.list_tools_and_save()

        assert client.tools is previous_tools

    @pytest.mark.asyncio
    async def test_later_page_cancellation_propagates_without_changing_tools(self):
        session = AsyncMock()
        session.list_tools.side_effect = [
            _page(["alpha"], "page-2"),
            asyncio.CancelledError(),
        ]
        client = _client(session)
        previous_tools = [SimpleNamespace(name="existing")]
        client.tools = previous_tools

        with pytest.raises(asyncio.CancelledError):
            await client.list_tools_and_save()

        assert client.tools is previous_tools
