import socket
from contextlib import AsyncExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import Tool
from mcp.types.version import LATEST_PROTOCOL_VERSION

from astrbot.core.agent import mcp_client as mcp_client_module
from astrbot.core.agent.mcp_client import (
    MCPClient,
    MCPTool,
    MCPToolNameAllocationError,
    MCPToolNameAllocator,
    _normalize_mcp_input_schema,
)
from astrbot.core.agent.tool import get_tool_id
from astrbot.core.tools.function_tool_manager import FunctionToolManager


class TestNormalizeMcpInputSchema:
    def test_lifts_property_level_required_booleans_to_parent_required_array(self):
        schema = {
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "required": True},
                "market": {"type": "string", "required": False},
            },
        }

        normalized = _normalize_mcp_input_schema(schema)

        assert normalized["required"] == ["stock_code"]
        assert "required" not in normalized["properties"]["stock_code"]
        assert "required" not in normalized["properties"]["market"]
        assert schema["properties"]["stock_code"]["required"] is True

    def test_preserves_existing_required_arrays_while_fixing_nested_objects(self):
        schema = {
            "type": "object",
            "required": ["server"],
            "properties": {
                "server": {
                    "type": "object",
                    "required": ["transport"],
                    "properties": {
                        "transport": {"type": "string"},
                        "stock_code": {"type": "string", "required": True},
                        "market": {"type": "string", "required": False},
                    },
                }
            },
        }

        normalized = _normalize_mcp_input_schema(schema)

        assert normalized["required"] == ["server"]
        assert normalized["properties"]["server"]["required"] == [
            "transport",
            "stock_code",
        ]
        assert (
            "required"
            not in normalized["properties"]["server"]["properties"]["stock_code"]
        )
        assert (
            "required" not in normalized["properties"]["server"]["properties"]["market"]
        )

    def test_preserves_parent_required_flag_for_nested_object_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "server": {
                    "type": "object",
                    "required": True,
                    "properties": {
                        "transport": {"type": "string", "required": True},
                    },
                }
            },
        }

        normalized = _normalize_mcp_input_schema(schema)

        assert normalized["required"] == ["server"]
        assert normalized["properties"]["server"]["required"] == ["transport"]
        assert (
            "required"
            not in normalized["properties"]["server"]["properties"]["transport"]
        )

    def test_ignores_non_boolean_required_values_and_non_dict_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "server": "invalid-property-schema",
                "market": {"type": "string", "required": "yes"},
                "stock_code": {"type": "string", "required": True},
            },
        }

        normalized = _normalize_mcp_input_schema(schema)

        assert normalized["required"] == ["stock_code"]
        assert normalized["properties"]["server"] == "invalid-property-schema"
        assert normalized["properties"]["market"]["required"] == "yes"
        assert "required" not in normalized["properties"]["stock_code"]
        assert schema["properties"]["server"] == "invalid-property-schema"
        assert schema["properties"]["market"]["required"] == "yes"


class TestMCPToolSchemaNormalization:
    def test_mcp_tool_accepts_property_level_required_booleans(self):
        mcp_tool = Tool(
            name="quote_lookup",
            description="Lookup a quote",
            inputSchema={
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "required": True},
                    "market": {"type": "string", "required": False},
                },
            },
        )

        tool = MCPTool(mcp_tool, MagicMock(), "gf-securities")

        assert tool.parameters["required"] == ["stock_code"]
        assert "required" not in tool.parameters["properties"]["stock_code"]
        assert "required" not in tool.parameters["properties"]["market"]

    def test_mcp_tool_keeps_sdk2_metadata_separate_from_input_schema(self):
        mcp_tool = Tool(
            name="report",
            title="Create report",
            description="Create a report",
            inputSchema={"type": "object", "properties": {}},
            outputSchema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
            },
            _meta={"source": "test"},
        )

        tool = MCPTool(mcp_tool, MagicMock(), "reports")

        assert tool.title == "Create report"
        assert tool.input_schema == {"type": "object", "properties": {}}
        assert tool.output_schema == {
            "type": "object",
            "properties": {"url": {"type": "string"}},
        }
        assert tool.meta == {"source": "test"}
        assert "url" not in tool.parameters["properties"]

    def test_mcp_tool_uses_a_safe_name_and_keeps_original_call_name(self):
        mcp_tool = Tool(
            name="t_drive.create/doc",
            description="Create a doc",
            inputSchema={"type": "object", "properties": {}},
        )

        tool = MCPTool(mcp_tool, MagicMock(), "tencent-docs")

        assert len(tool.name) <= 64
        assert tool.name
        assert all(
            char.isascii() and (char.isalnum() or char in "_-") for char in tool.name
        )
        assert tool.mcp_tool_name == "t_drive.create/doc"
        assert get_tool_id(tool) == "mcp:tencent-docs:t_drive.create/doc"

    @pytest.mark.asyncio
    async def test_mcp_tool_calls_the_original_name(self):
        mcp_tool = Tool(
            name="t_drive.create/doc",
            description="Create a doc",
            inputSchema={"type": "object", "properties": {}},
        )
        client = SimpleNamespace(
            _interaction_coordinator=None,
            call_tool=AsyncMock(return_value="ok"),
        )
        tool = MCPTool(mcp_tool, client, "tencent-docs")

        result = await tool.call(SimpleNamespace(tool_call_timeout=7), title="A")

        assert result == "ok"
        client.call_tool.assert_awaited_once_with(
            "t_drive.create/doc", {"title": "A"}, 7
        )


def _mcp_tool(name: str):
    return Tool(
        name=name,
        description="Test MCP tool",
        inputSchema={"type": "object", "properties": {}},
    )


def test_mcp_name_allocator_avoids_illegal_character_and_server_collisions():
    allocator = MCPToolNameAllocator()

    dotted = allocator.allocate("alpha", "a.b")
    underscored = allocator.allocate("alpha", "a_b")
    other_server = allocator.allocate("beta", "a.b")
    long_name = allocator.allocate("alpha", "x" * 300)

    assert len({dotted, underscored, other_server, long_name}) == 4
    for name in (dotted, underscored, other_server, long_name):
        assert 1 <= len(name) <= 64
        assert all(char.isascii() and (char.isalnum() or char in "_-") for char in name)


def test_mcp_name_allocator_reuses_a_mapping_across_reconnect_order():
    allocator = MCPToolNameAllocator()
    first = allocator.allocate("first", "a.b")
    second = allocator.allocate("second", "a.b")

    assert allocator.allocate("second", "a.b") == second
    assert allocator.allocate("first", "a.b") == first


def test_mcp_name_allocator_rejects_an_ambiguous_candidate():
    allocator = MCPToolNameAllocator(lambda _server, _tool: "mcp_fixed")
    assert allocator.allocate("first", "one") == "mcp_fixed"

    with pytest.raises(MCPToolNameAllocationError, match="collision"):
        allocator.allocate("second", "two")


def test_mcp_tool_registration_is_stable_and_refuses_empty_names():
    manager = FunctionToolManager()
    client = MagicMock()
    client.tools = [_mcp_tool("a.b"), _mcp_tool("a_b"), _mcp_tool("")]

    first_registered = manager._register_mcp_tools("alpha", client)
    first_names = [tool.name for tool in first_registered]
    assert len(first_names) == 2
    assert [tool.mcp_tool_name for tool in first_registered] == ["a.b", "a_b"]

    client.tools = list(reversed(client.tools[:-1]))
    second_registered = manager._register_mcp_tools("alpha", client)
    assert {tool.mcp_tool_name: tool.name for tool in second_registered} == {
        tool.mcp_tool_name: tool.name for tool in first_registered
    }


@pytest.mark.asyncio
async def test_streamable_http_connection_uses_sdk2_client_without_initialize(
    monkeypatch,
):
    client = mcp_client_module.MCPClient()
    client._server_name = "demo"
    calls: list[dict] = []

    class FakeClient:
        protocol_version = "2026-07-28"
        server_capabilities = SimpleNamespace(model_dump=lambda **_kwargs: {})

        def __init__(self, transport, **kwargs):
            calls.append({"transport": transport, **kwargs})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(mcp_client_module, "Client", FakeClient)
    monkeypatch.setattr(
        mcp_client_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            )
        ],
    )

    stack = AsyncExitStack()
    opened = await client._open_client(
        stack,
        {
            "url": "https://example.com/mcp",
            "transport": "streamable_http",
            "headers": {"X-Test": "1"},
            "connect_timeout_seconds": 12,
            "read_timeout_seconds": 56,
            "terminate_on_close": False,
        },
        "demo",
    )

    assert opened.protocol_version == "2026-07-28"
    assert calls[0]["mode"] == "2026-07-28"
    assert not hasattr(opened, "initialize")
    await stack.aclose()


@pytest.mark.asyncio
async def test_sdk2_in_memory_server_uses_modern_client_without_initialize():
    server = MCPServer("modern-test")

    @server.tool()
    def echo(value: str) -> str:
        return value

    async with Client(server, mode=LATEST_PROTOCOL_VERSION) as sdk_client:
        assert sdk_client.protocol_version == "2026-07-28"
        assert [tool.name for tool in (await sdk_client.list_tools()).tools] == ["echo"]
        result = await sdk_client.call_tool("echo", {"value": "hello"})

    assert result.structured_content == {"result": "hello"}


@pytest.mark.asyncio
async def test_mcp_catalog_pagination_is_atomic_and_rejects_repeated_cursors():
    class PagedClient:
        def __init__(self):
            self.cursors: list[str | None] = []

        async def list_tools(self, *, cursor=None):
            self.cursors.append(cursor)
            if cursor is None:
                return SimpleNamespace(
                    tools=[Tool(name="one", inputSchema={})], next_cursor="next"
                )
            return SimpleNamespace(
                tools=[Tool(name="two", inputSchema={})], next_cursor=None
            )

    client = MCPClient()
    client.client = PagedClient()  # type: ignore[assignment]

    assert [tool.name for tool in await client.list_tools_and_save()] == ["one", "two"]
    assert client.client.cursors == [None, "next"]  # type: ignore[union-attr]

    class RepeatingClient:
        async def list_tools(self, *, cursor=None):
            return SimpleNamespace(
                tools=[Tool(name="bad", inputSchema={})], next_cursor="same"
            )

    old_tools = client.tools
    client.client = RepeatingClient()  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="repeated"):
        await client.list_tools_and_save()
    assert client.tools is old_tools


@pytest.mark.asyncio
async def test_catalog_subscription_limit_does_not_reconnect_healthy_client():
    class RejectedSubscription:
        async def __aenter__(self):
            raise MCPError(-32603, "Subscription limit reached")

        async def __aexit__(self, *_args):
            return False

    class RejectingClient:
        def listen(self, **_kwargs):
            return RejectedSubscription()

    client = MCPClient()
    client._server_name = "context7"

    await client._watch_catalog(RejectingClient())  # type: ignore[arg-type]

    assert not client._reconnect_event.is_set()
