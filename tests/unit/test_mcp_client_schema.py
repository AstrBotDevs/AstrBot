from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

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

    def test_mcp_tool_sanitizes_llm_facing_name_but_keeps_original_for_call(self):
        mcp_tool = SimpleNamespace(
            name="t_drive.create_doc",
            description="Create a doc",
            inputSchema={"type": "object", "properties": {}},
        )

        tool = MCPTool(mcp_tool, MagicMock(), "tencent-docs")

        # The name exposed to the LLM must match the OpenAI/Anthropic
        # [a-zA-Z0-9_-] pattern; the original dotted name is preserved for the
        # actual MCP call.
        assert tool.name == "t_drive_create_doc"
        assert tool.mcp_tool.name == "t_drive.create_doc"


class TestMCPToolArgumentForwarding:
    """Empty placeholders for optional slots must not reach the MCP server (#7116)."""

    DEFAULT_SCHEMA = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "area": {"type": "string"},
            "floor": {"type": "string"},
            "domain": {"type": "array"},
            "device_class": {"type": "array"},
        },
    }

    @classmethod
    def _tool(cls, client, input_schema=None):
        mcp_tool = SimpleNamespace(
            name="HassTurnOn",
            description="Turn on a device",
            inputSchema=input_schema or cls.DEFAULT_SCHEMA,
        )
        return MCPTool(mcp_tool, client, "home-assistant")

    @pytest.mark.asyncio
    async def test_drops_empty_optional_arguments(self):
        client = MagicMock()
        client.call_tool_with_reconnect = AsyncMock(return_value="ok")
        tool = self._tool(client)

        await tool.call(
            SimpleNamespace(tool_call_timeout=30),
            name="Demo Light",
            area="",
            floor="",
            domain=[],
            device_class=[],
        )

        forwarded = client.call_tool_with_reconnect.await_args.kwargs["arguments"]
        assert forwarded == {"name": "Demo Light"}

    @pytest.mark.asyncio
    async def test_keeps_empty_required_arguments(self):
        client = MagicMock()
        client.call_tool_with_reconnect = AsyncMock(return_value="ok")
        tool = self._tool(client)

        await tool.call(SimpleNamespace(tool_call_timeout=30), name="", area="")

        forwarded = client.call_tool_with_reconnect.await_args.kwargs["arguments"]
        assert forwarded == {"name": ""}

    @pytest.mark.asyncio
    async def test_keeps_falsy_values_that_are_not_empty(self):
        client = MagicMock()
        client.call_tool_with_reconnect = AsyncMock(return_value="ok")
        tool = self._tool(client)

        await tool.call(
            SimpleNamespace(tool_call_timeout=30),
            name="Demo Light",
            area=0,
            floor=False,
        )

        forwarded = client.call_tool_with_reconnect.await_args.kwargs["arguments"]
        assert forwarded == {"name": "Demo Light", "area": 0, "floor": False}

    @pytest.mark.asyncio
    async def test_drops_empty_optional_arguments_in_nested_objects(self):
        client = MagicMock()
        client.call_tool_with_reconnect = AsyncMock(return_value="ok")
        tool = self._tool(
            client,
            {
                "type": "object",
                "required": ["scene"],
                "properties": {
                    "scene": {"type": "string"},
                    "options": {
                        "type": "object",
                        "required": ["mode"],
                        "properties": {
                            "mode": {"type": "string"},
                            "note": {"type": "string"},
                        },
                    },
                },
            },
        )

        await tool.call(
            SimpleNamespace(tool_call_timeout=30),
            scene="movie",
            options={"mode": "dim", "note": ""},
        )

        forwarded = client.call_tool_with_reconnect.await_args.kwargs["arguments"]
        assert forwarded == {"scene": "movie", "options": {"mode": "dim"}}

    @pytest.mark.asyncio
    async def test_keeps_values_when_requiredness_is_conditional(self):
        client = MagicMock()
        client.call_tool_with_reconnect = AsyncMock(return_value="ok")
        tool = self._tool(
            client,
            {
                "type": "object",
                "dependentRequired": {"mode": ["note"]},
                "properties": {
                    "mode": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        )

        await tool.call(
            SimpleNamespace(tool_call_timeout=30),
            mode="dim",
            note="",
        )

        forwarded = client.call_tool_with_reconnect.await_args.kwargs["arguments"]
        assert forwarded == {"mode": "dim", "note": ""}
