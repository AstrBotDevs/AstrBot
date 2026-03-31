from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import mcp
from astrbot.core.agent.mcp_resource_bridge import (
    MCPListResourceTemplatesTool,
    MCPListResourcesTool,
    MCPReadResourceTool,
    build_mcp_resource_tool_names,
    shape_read_resource_result,
)
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.provider.func_tool_manager import (
    FunctionToolManager,
    _MCPServerRuntime,
)


class _FakeResourceCapableMCPClient:
    def __init__(self) -> None:
        self.name: str | None = None
        self.tools = [
            mcp.types.Tool(
                name="draft_brief",
                description="Draft a short brief.",
                inputSchema={"type": "object", "properties": {}},
            )
        ]
        self.resource_templates_supported = True
        self.resource_bridge_tool_names: list[str] = []
        self.prompt_bridge_tool_names: list[str] = []
        self.server_errlogs: list[str] = []

    @property
    def supports_resources(self) -> bool:
        return True

    @property
    def supports_prompts(self) -> bool:
        return False

    async def connect_to_server(self, config: dict, name: str) -> None:
        _ = config
        self.name = name

    async def list_tools_and_save(self) -> mcp.types.ListToolsResult:
        return mcp.types.ListToolsResult(tools=self.tools)

    async def load_resource_capabilities(self) -> None:
        self.resource_bridge_tool_names = build_mcp_resource_tool_names(
            self.name or "server",
            include_templates=True,
        )

    async def load_prompt_capabilities(self) -> None:
        self.prompt_bridge_tool_names = []

    async def list_resources_and_save(
        self,
        cursor: str | None = None,
    ) -> mcp.types.ListResourcesResult:
        _ = cursor
        return mcp.types.ListResourcesResult(
            resources=[
                mcp.types.Resource(
                    name="team_notes",
                    uri="memo://team/notes",
                    description="Shared team notes",
                    mimeType="text/plain",
                )
            ]
        )

    async def list_resource_templates_and_save(
        self,
        cursor: str | None = None,
    ) -> mcp.types.ListResourceTemplatesResult:
        _ = cursor
        self.resource_templates_supported = True
        return mcp.types.ListResourceTemplatesResult(
            resourceTemplates=[
                mcp.types.ResourceTemplate(
                    name="note_by_id",
                    uriTemplate="memo://notes/{id}",
                    description="Read a note by id",
                    mimeType="text/plain",
                )
            ]
        )

    async def read_resource_with_reconnect(
        self,
        uri: str,
        read_timeout_seconds,
    ) -> mcp.types.ReadResourceResult:
        _ = read_timeout_seconds
        return mcp.types.ReadResourceResult(
            contents=[
                mcp.types.TextResourceContents(
                    uri=uri,
                    mimeType="text/plain",
                    text="hello from resource",
                )
            ]
        )

    async def cleanup(self) -> None:
        return None


@pytest.mark.asyncio
async def test_resource_bridge_tools_are_registered_and_removed(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "astrbot.core.provider.func_tool_manager.MCPClient",
        _FakeResourceCapableMCPClient,
    )

    tool_mgr = FunctionToolManager()
    client = await tool_mgr._init_mcp_client(
        "demo-server",
        {"command": "node", "args": ["stdio.js"]},
    )

    tool_names = {tool.name for tool in tool_mgr.func_list}
    assert "draft_brief" in tool_names
    assert "mcp_demo_server_list_resources" in tool_names
    assert "mcp_demo_server_read_resource" in tool_names
    assert "mcp_demo_server_list_resource_templates" in tool_names

    completed_task = asyncio.create_task(asyncio.sleep(0))
    await completed_task
    tool_mgr._mcp_server_runtime["demo-server"] = _MCPServerRuntime(
        name="demo-server",
        client=client,
        shutdown_event=asyncio.Event(),
        lifecycle_task=completed_task,
    )

    await tool_mgr._terminate_mcp_client("demo-server")

    assert not any(
        getattr(tool, "mcp_server_name", None) == "demo-server"
        for tool in tool_mgr.func_list
    )


@pytest.mark.asyncio
async def test_resource_listing_tools_return_text_summaries():
    client = _FakeResourceCapableMCPClient()
    list_tool = MCPListResourcesTool(
        mcp_client=client,
        mcp_server_name="demo-server",
    )
    template_tool = MCPListResourceTemplatesTool(
        mcp_client=client,
        mcp_server_name="demo-server",
    )
    context = ContextWrapper(context=SimpleNamespace())

    list_result = await list_tool.call(context)
    template_result = await template_tool.call(context)

    assert isinstance(list_result.content[0], mcp.types.TextContent)
    assert "memo://team/notes" in list_result.content[0].text
    assert isinstance(template_result.content[0], mcp.types.TextContent)
    assert "memo://notes/{id}" in template_result.content[0].text


@pytest.mark.asyncio
async def test_read_resource_tool_returns_text_resource_summary():
    client = _FakeResourceCapableMCPClient()
    tool = MCPReadResourceTool(
        mcp_client=client,
        mcp_server_name="demo-server",
    )
    context = ContextWrapper(context=SimpleNamespace(), tool_call_timeout=30)

    result = await tool.call(context, uri="memo://team/notes")

    assert isinstance(result.content[0], mcp.types.TextContent)
    assert "hello from resource" in result.content[0].text
    assert "memo://team/notes" in result.content[0].text


def test_shape_read_resource_result_returns_embedded_image_for_single_image_blob():
    response = mcp.types.ReadResourceResult(
        contents=[
            mcp.types.BlobResourceContents(
                uri="memo://images/cover",
                mimeType="image/png",
                blob="ZmFrZQ==",
            )
        ]
    )

    result = shape_read_resource_result(
        server_name="demo-server",
        requested_uri="memo://images/cover",
        response=response,
    )

    assert isinstance(result.content[0], mcp.types.EmbeddedResource)
    assert result.content[0].resource.mimeType == "image/png"


def test_shape_read_resource_result_summarizes_multi_part_content():
    response = mcp.types.ReadResourceResult(
        contents=[
            mcp.types.TextResourceContents(
                uri="memo://notes/1",
                mimeType="text/plain",
                text="first part",
            ),
            mcp.types.BlobResourceContents(
                uri="memo://notes/1.bin",
                mimeType="application/octet-stream",
                blob="Zm9v",
            ),
        ]
    )

    result = shape_read_resource_result(
        server_name="demo-server",
        requested_uri="memo://notes/1",
        response=response,
    )

    assert isinstance(result.content[0], mcp.types.TextContent)
    assert "Returned parts: 2" in result.content[0].text
    assert "Binary blob returned" in result.content[0].text
