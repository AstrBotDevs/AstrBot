import importlib.metadata
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent import mcp_client
from astrbot.core.agent.mcp_client import MCPTool, _normalize_mcp_input_schema


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

    @pytest.mark.asyncio
    async def test_mcp_tool_sanitizes_llm_facing_name_but_keeps_original_for_call(self):
        mcp_tool = SimpleNamespace(
            name="t_drive.create_doc",
            description="Create a doc",
            inputSchema={"type": "object", "properties": {}},
        )

        client = SimpleNamespace(call_tool_with_reconnect=AsyncMock())
        tool = MCPTool(mcp_tool, client, "tencent-docs")

        assert re.fullmatch(r"mcp__tencent-docs__t_drive_create_doc_[0-9a-f]{12}", tool.name)
        await tool.call(SimpleNamespace(tool_call_timeout=30), title="Example")
        assert client.call_tool_with_reconnect.call_args.kwargs["tool_name"] == "t_drive.create_doc"

    def test_mcp_tool_names_distinguish_servers_and_unicode_tools(self):
        def name(server, tool):
            return MCPTool(
                SimpleNamespace(name=tool, description="", inputSchema={}),
                MagicMock(),
                server,
            ).name

        assert name("github", "search") == "mcp__github__search"
        assert name("calendar", "search") == "mcp__calendar__search"
        assert re.fullmatch(r"mcp__[a-z]{6}__search", name("知识库", "search"))
        assert name("知识库", "search") == name("知识库", "search")
        assert name("知识库", "search") != name("资料库", "search")
        assert name("知识库", "搜索") != name("知识库", "查询")
        assert len(name("github", "x" * 100)) == 64


@pytest.mark.asyncio
async def test_connect_to_server_rejects_unsupported_mcp_major(monkeypatch):
    monkeypatch.setattr(
        mcp_client,
        "importlib_metadata",
        SimpleNamespace(
            version=lambda _name: "2.3.0",
            PackageNotFoundError=importlib.metadata.PackageNotFoundError,
        ),
    )
    client = mcp_client.MCPClient()

    with pytest.raises(RuntimeError, match=r"mcp 2\.3\.0"):
        await client.connect_to_server({"command": "bash"}, "demo_server")

    assert client._connection_task is None
