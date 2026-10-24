import asyncio
from unittest.mock import AsyncMock

import anyio
import pytest
from mcp import ClientSession, types
from mcp.shared.message import SessionMessage

from astrbot.core.agent.mcp_client import MCPClient, MCPTool


def make_tool(name: str, output_schema: dict | None = None) -> types.Tool:
    return types.Tool(
        name=name,
        description=name,
        inputSchema={"type": "object", "properties": {}},
        outputSchema=output_schema,
    )


@pytest.mark.asyncio
async def test_list_tools_and_save_returns_single_page_result_with_metadata():
    client = MCPClient()
    first = types.ListToolsResult(
        _meta={"origin": "server"}, tools=[make_tool("first")]
    )
    client.session = AsyncMock()
    client.session.list_tools.return_value = first

    result = await client.list_tools_and_save()

    assert result.tools == first.tools
    assert result.nextCursor is None
    assert result.meta == {"origin": "server"}
    assert client.tools == first.tools
    client.session.list_tools.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_list_tools_and_save_aggregates_pages_including_empty_page():
    client = MCPClient()
    first = types.ListToolsResult(
        _meta={"origin": "first"}, nextCursor="page-2", tools=[make_tool("one")]
    )
    second = types.ListToolsResult(nextCursor="page-3", tools=[])
    third = types.ListToolsResult(tools=[make_tool("three")])
    client.session = AsyncMock()
    client.session.list_tools.side_effect = [first, second, third]

    result = await client.list_tools_and_save()

    assert [tool.name for tool in result.tools] == ["one", "three"]
    assert result.meta == {"origin": "first"}
    assert result.nextCursor is None
    assert client.tools == result.tools
    assert [call.args for call in client.session.list_tools.await_args_list] == [
        (),
        (),
        (),
    ]
    assert [call.kwargs for call in client.session.list_tools.await_args_list] == [
        {},
        {"cursor": "page-2"},
        {"cursor": "page-3"},
    ]


@pytest.mark.asyncio
async def test_list_tools_failure_keeps_previous_cache():
    client = MCPClient()
    client.tools = [make_tool("cached")]
    client.session = AsyncMock()
    client.session.list_tools.side_effect = [
        types.ListToolsResult(nextCursor="next", tools=[make_tool("partial")]),
        ValueError("server failed"),
    ]

    with pytest.raises(ValueError, match="server failed"):
        await client.list_tools_and_save()

    assert [tool.name for tool in client.tools] == ["cached"]


@pytest.mark.asyncio
async def test_list_tools_cancellation_keeps_previous_cache():
    client = MCPClient()
    client.tools = [make_tool("cached")]
    client.session = AsyncMock()

    async def cancel_on_page(cursor=None):
        if cursor is None:
            return types.ListToolsResult(
                nextCursor="next", tools=[make_tool("partial")]
            )
        raise asyncio.CancelledError

    client.session.list_tools.side_effect = cancel_on_page

    with pytest.raises(asyncio.CancelledError):
        await client.list_tools_and_save()

    assert [tool.name for tool in client.tools] == ["cached"]


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor", ["repeat", "page\r\nFORGED LOG\x1b[0m"])
async def test_list_tools_repeated_cursor_fails_without_changing_cache(cursor):
    client = MCPClient()
    client.tools = [make_tool("cached")]
    client.session = AsyncMock()
    client.session.list_tools.side_effect = [
        types.ListToolsResult(nextCursor=cursor, tools=[]),
        types.ListToolsResult(nextCursor=cursor, tools=[]),
    ]

    with pytest.raises(RuntimeError, match="repeated tools/list cursor") as exc_info:
        await client.list_tools_and_save()

    assert str(exc_info.value) == f"MCP server repeated tools/list cursor: {cursor!r}"
    assert not any(char in str(exc_info.value) for char in "\r\n\x1b")
    assert [tool.name for tool in client.tools] == ["cached"]


@pytest.mark.asyncio
@pytest.mark.parametrize("split_pages", [False, True])
@pytest.mark.parametrize("second_name", ["foo_bar", "foo.bar"])
async def test_list_tools_rejects_normalized_name_collisions_without_changing_cache(
    split_pages,
    second_name,
):
    client = MCPClient()
    cached = [make_tool("cached")]
    client.tools = cached
    conflicting = [make_tool("foo.bar"), make_tool(second_name, {"type": "string"})]
    pages = (
        [
            types.ListToolsResult(nextCursor="next", tools=conflicting[:1]),
            types.ListToolsResult(tools=conflicting[1:]),
        ]
        if split_pages
        else [types.ListToolsResult(tools=conflicting)]
    )
    client.session = AsyncMock()
    client.session.list_tools.side_effect = pages

    with pytest.raises(ValueError) as exc_info:
        await client.list_tools_and_save()

    assert str(exc_info.value) == (
        f"MCP tool names 'foo.bar' and {second_name!r} both normalize to 'foo_bar'"
    )
    assert client.tools is cached


@pytest.mark.asyncio
async def test_list_tools_preserves_distinct_original_names_after_normalization():
    client = MCPClient()
    client.session = AsyncMock()
    client.session.list_tools.side_effect = [
        types.ListToolsResult(nextCursor="next", tools=[make_tool("foo.bar")]),
        types.ListToolsResult(tools=[make_tool("foo-baz")]),
    ]

    result = await client.list_tools_and_save()

    wrapped = [MCPTool(tool, client, "server") for tool in result.tools]
    assert [tool.name for tool in wrapped] == ["foo_bar", "foo-baz"]
    assert [tool.mcp_tool.name for tool in wrapped] == ["foo.bar", "foo-baz"]
    assert client.tools == result.tools


@pytest.mark.asyncio
async def test_list_tools_uses_native_session_cursor_serialization_and_schema_cache():
    client = MCPClient()
    read_send, read_receive = anyio.create_memory_object_stream(2)
    write_send, write_receive = anyio.create_memory_object_stream(2)
    expected_tools = [
        make_tool("one", {"type": "object", "properties": {"one": {}}}),
        make_tool("two", {"type": "object", "properties": {"two": {}}}),
    ]

    async def mocked_server():
        for index, expected_cursor in enumerate((None, "next")):
            request = await write_receive.receive()
            request_data = request.message.root.model_dump(
                by_alias=True, mode="json", exclude_none=True
            )
            assert request_data["method"] == "tools/list"
            if expected_cursor is None:
                assert "params" not in request_data
            else:
                assert request_data["params"]["cursor"] == expected_cursor

            response = types.JSONRPCResponse(
                jsonrpc="2.0",
                id=request.message.root.id,
                result={
                    "tools": [
                        expected_tools[index].model_dump(by_alias=True, mode="json")
                    ],
                    "nextCursor": "next" if index == 0 else None,
                },
            )
            await read_send.send(SessionMessage(message=types.JSONRPCMessage(response)))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(mocked_server)
        async with ClientSession(read_receive, write_send) as session:
            client.session = session
            result = await client.list_tools_and_save()

    assert [tool.name for tool in result.tools] == ["one", "two"]
    assert session._tool_output_schemas == {
        "one": expected_tools[0].outputSchema,
        "two": expected_tools[1].outputSchema,
    }
    assert [tool.name for tool in client.tools] == ["one", "two"]
