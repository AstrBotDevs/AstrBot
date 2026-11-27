import importlib.metadata
from types import SimpleNamespace
from unittest.mock import MagicMock

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


@pytest.mark.asyncio
async def test_concurrent_call_tool_failures_trigger_single_reconnect():
    """Concurrent failures on the same broken generation only reconnect once."""
    import asyncio
    from datetime import timedelta

    import anyio

    client = mcp_client.MCPClient()
    client._mcp_server_config = {"command": "python"}
    client._server_name = "demo"
    client._connection_generation = 1

    broken_session = SimpleNamespace()
    reconnected_session = SimpleNamespace()
    reconnect_calls = 0

    async def broken_call_tool(**_kwargs):
        raise anyio.ClosedResourceError()

    async def healthy_call_tool(name, arguments, read_timeout_seconds):  # noqa: ARG001
        return f"ok:{arguments['x']}"

    broken_session.call_tool = broken_call_tool
    reconnected_session.call_tool = healthy_call_tool
    client.session = broken_session  # type: ignore[assignment]

    async def fake_connect(_cfg, _name):
        nonlocal reconnect_calls
        reconnect_calls += 1
        await asyncio.sleep(0.02)
        client.session = reconnected_session  # type: ignore[assignment]

    async def fake_list_tools():
        return SimpleNamespace(tools=[])

    client.connect_to_server = fake_connect  # type: ignore[method-assign]
    client.list_tools_and_save = fake_list_tools  # type: ignore[method-assign]

    res1, res2, res3 = await asyncio.gather(
        client.call_tool_with_reconnect("ping", {"x": 1}, timedelta(seconds=5)),
        client.call_tool_with_reconnect("ping", {"x": 2}, timedelta(seconds=5)),
        client.call_tool_with_reconnect("ping", {"x": 3}, timedelta(seconds=5)),
    )

    assert [res1, res2, res3] == ["ok:1", "ok:2", "ok:3"]
    assert reconnect_calls == 1
    assert client._connection_generation == 2


@pytest.mark.asyncio
async def test_failed_reconnect_clears_partial_session_so_next_caller_retries():
    """If list_tools_and_save fails after connect, session is cleared for retry."""
    client = mcp_client.MCPClient()
    client._mcp_server_config = {"command": "python"}
    client._server_name = "demo"
    client._connection_generation = 1

    partial_session = SimpleNamespace()

    async def fake_connect(_cfg, _name):
        client.session = partial_session  # type: ignore[assignment]
        client._connection_generation += 1

    attempts = 0

    async def flaky_list_tools():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("list tools failed")
        return SimpleNamespace(tools=[])

    client.connect_to_server = fake_connect  # type: ignore[method-assign]
    client.list_tools_and_save = flaky_list_tools  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="list tools failed"):
        await client._reconnect(failed_generation=1)
    assert client.session is None

    # Second waiting caller must still attempt reconnect instead of skipping.
    await client._reconnect(failed_generation=1)
    assert client.session is partial_session
    assert attempts == 2


def test_server_errlogs_is_bounded():
    """Server error log buffer stays a plain list capped at the newest entries."""
    client = mcp_client.MCPClient()
    limit = mcp_client.MCPClient._MAX_SERVER_ERRLOGS
    for idx in range(limit + 35):
        client._append_server_errlog(f"line-{idx}")

    assert isinstance(client.server_errlogs, list)
    assert len(client.server_errlogs) == limit
    assert client.server_errlogs[0] == "line-35"
    assert client.server_errlogs[-1] == f"line-{limit + 34}"
