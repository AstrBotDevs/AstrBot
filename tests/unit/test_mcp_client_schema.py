import socket
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent import mcp_client as mcp_client_module
from astrbot.core.agent.mcp_client import (
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
        mcp_tool = SimpleNamespace(
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

    def test_mcp_tool_uses_a_safe_name_and_keeps_original_call_name(self):
        mcp_tool = SimpleNamespace(
            name="t_drive.create/doc",
            description="Create a doc",
            inputSchema={"type": "object", "properties": {}},
        )

        tool = MCPTool(mcp_tool, MagicMock(), "tencent-docs")

        assert len(tool.name) <= 64
        assert tool.name
        assert all(char.isascii() and (char.isalnum() or char in "_-") for char in tool.name)
        assert tool.mcp_tool_name == "t_drive.create/doc"
        assert get_tool_id(tool) == "mcp:tencent-docs:t_drive.create/doc"

    @pytest.mark.asyncio
    async def test_mcp_tool_calls_the_original_name(self):
        mcp_tool = SimpleNamespace(
            name="t_drive.create/doc",
            description="Create a doc",
            inputSchema={"type": "object", "properties": {}},
        )
        client = MagicMock()
        client.call_tool_with_reconnect = AsyncMock(return_value="ok")
        tool = MCPTool(mcp_tool, client, "tencent-docs")

        result = await tool.call(SimpleNamespace(tool_call_timeout=7), title="A")

        assert result == "ok"
        client.call_tool_with_reconnect.assert_awaited_once_with(
            tool_name="t_drive.create/doc",
            arguments={"title": "A"},
            read_timeout_seconds=7,
        )


def _mcp_tool(name: str):
    return SimpleNamespace(
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
async def test_streamable_http_connection_uses_native_http_client_path(monkeypatch):
    client = mcp_client_module.MCPClient()
    session = MagicMock()
    session.initialize = AsyncMock()

    quick_test = AsyncMock(return_value=(True, ""))
    monkeypatch.setattr(mcp_client_module, "_quick_test_mcp_connection", quick_test)

    transport_calls: list[dict] = []

    @asynccontextmanager
    async def fake_streamable_http_client(
        url: str,
        *,
        http_client,
        terminate_on_close: bool = True,
    ):
        transport_calls.append(
            {
                "url": url,
                "http_client": http_client,
                "terminate_on_close": terminate_on_close,
            }
        )
        yield ("read-stream", "write-stream")

    @asynccontextmanager
    async def fake_client_session(*args, **kwargs):
        assert args == ()
        assert kwargs["read_stream"] == "read-stream"
        assert kwargs["write_stream"] == "write-stream"
        yield session

    monkeypatch.setattr(
        mcp_client_module,
        "streamable_http_client",
        fake_streamable_http_client,
    )
    monkeypatch.setattr(
        mcp_client_module,
        "mcp",
        SimpleNamespace(ClientSession=fake_client_session),
    )
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

    await client.connect_to_server(
        {
            "url": "https://example.com/mcp",
            "transport": "streamable_http",
            "headers": {"X-Test": "1"},
            "timeout": 12,
            "sse_read_timeout": 34,
            "session_read_timeout": 56,
            "terminate_on_close": False,
        },
        "demo",
    )

    assert quick_test.await_count == 1
    assert len(transport_calls) == 1
    assert transport_calls[0]["url"] == "https://example.com/mcp"
    assert transport_calls[0]["terminate_on_close"] is False
    assert transport_calls[0]["http_client"].headers["x-test"] == "1"
    session.initialize.assert_awaited_once()

    await client.cleanup()
