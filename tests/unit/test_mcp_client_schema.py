import socket
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent import mcp_client as mcp_client_module
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
