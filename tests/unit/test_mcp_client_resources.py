from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest

from astrbot.core.agent.mcp_client import MCPClient


def _resource_client(session=None):
    client = MCPClient()
    client.session = session or AsyncMock()
    client._server_capabilities = SimpleNamespace(resources=object())
    return client


class TestMCPResourceCapabilities:
    @pytest.mark.asyncio
    async def test_initialize_saves_server_capabilities(self):
        capabilities = SimpleNamespace(resources=object())
        session = AsyncMock()
        session.initialize.return_value = SimpleNamespace(capabilities=capabilities)
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
            ),
        ):
            await client._do_connect(
                {"command": "python", "args": []},
                "resource-server",
            )

        assert client._server_capabilities is capabilities
        assert client.supports_resources is True

    @pytest.mark.asyncio
    async def test_resource_operations_require_advertised_capability(self):
        session = AsyncMock()
        client = MCPClient()
        client.session = session

        with pytest.raises(RuntimeError, match="does not advertise resources"):
            await client.list_resources()

        session.list_resources.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cleanup_clears_resource_capability_state(self):
        client = _resource_client()

        await client.cleanup()

        assert client.supports_resources is False

    @pytest.mark.asyncio
    async def test_resource_only_server_does_not_receive_tools_list(self):
        session = AsyncMock()
        client = _resource_client(session)
        client._server_capabilities = SimpleNamespace(
            resources=object(),
            tools=None,
        )

        result = await client.list_tools_and_save()

        assert result.tools == []
        assert client.tools == []
        session.list_tools.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_capabilities_preserve_tools_list_behavior(self):
        session = AsyncMock()
        expected = SimpleNamespace(tools=[object()])
        session.list_tools.return_value = expected
        client = MCPClient()
        client.session = session

        result = await client.list_tools_and_save()

        assert result is expected
        assert client.tools == expected.tools
        session.list_tools.assert_awaited_once_with()


class TestMCPResourceListing:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method_name", "session_method_name"),
        [
            ("list_resources", "list_resources"),
            ("list_resource_templates", "list_resource_templates"),
        ],
    )
    async def test_listing_without_cursor_uses_sdk_1_8_compatible_call(
        self,
        method_name,
        session_method_name,
    ):
        session = AsyncMock()
        expected = object()
        getattr(session, session_method_name).return_value = expected
        client = _resource_client(session)

        result = await getattr(client, method_name)()

        assert result is expected
        getattr(session, session_method_name).assert_awaited_once_with()
        assert not hasattr(client, "resources")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method_name", "session_method_name"),
        [
            ("list_resources", "list_resources"),
            ("list_resource_templates", "list_resource_templates"),
        ],
    )
    async def test_listing_with_cursor_passes_cursor_keyword(
        self,
        method_name,
        session_method_name,
    ):
        session = AsyncMock()
        expected = object()
        getattr(session, session_method_name).return_value = expected
        client = _resource_client(session)

        result = await getattr(client, method_name)("next-page")

        assert result is expected
        getattr(session, session_method_name).assert_awaited_once_with(
            cursor="next-page"
        )

    @pytest.mark.asyncio
    async def test_cursor_on_unsupported_sdk_raises_clear_error(self):
        session = AsyncMock()
        session.list_resources.side_effect = TypeError(
            "got an unexpected keyword argument 'cursor'"
        )
        client = _resource_client(session)

        with pytest.raises(RuntimeError, match="does not support resource pagination"):
            await client.list_resources("next-page")

    @pytest.mark.asyncio
    async def test_listing_does_not_mask_sdk_type_errors(self):
        session = AsyncMock()
        session.list_resources.side_effect = TypeError("invalid response payload")
        client = _resource_client(session)

        with pytest.raises(TypeError, match="invalid response payload"):
            await client.list_resources("next-page")


class TestMCPResourceReading:
    @pytest.mark.asyncio
    async def test_read_resource_passes_uri_without_caching_content(self):
        session = AsyncMock()
        expected = object()
        session.read_resource.return_value = expected
        client = _resource_client(session)

        result = await client.read_resource("file:///docs/guide.md")

        assert result is expected
        session.read_resource.assert_awaited_once_with(uri="file:///docs/guide.md")
        assert not hasattr(client, "resources")

    @pytest.mark.asyncio
    async def test_read_resource_does_not_reconnect_after_closed_transport(self):
        session = AsyncMock()
        session.read_resource.side_effect = anyio.ClosedResourceError()
        client = _resource_client(session)
        client._reconnect = AsyncMock()

        with pytest.raises(anyio.ClosedResourceError):
            await client.read_resource("file:///docs/guide.md")

        session.read_resource.assert_awaited_once_with(uri="file:///docs/guide.md")
        client._reconnect.assert_not_awaited()
