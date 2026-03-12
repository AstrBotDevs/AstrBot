from __future__ import annotations

import asyncio
from types import SimpleNamespace

import mcp
import pytest

from astrbot.core.agent.mcp_prompt_bridge import (
    MCPGetPromptTool,
    MCPListPromptsTool,
    build_mcp_prompt_tool_names,
    shape_get_prompt_result,
)
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.provider.func_tool_manager import (
    FunctionToolManager,
    _MCPServerRuntime,
)


class _FakePromptCapableMCPClient:
    def __init__(self) -> None:
        self.name: str | None = None
        self.tools = [
            mcp.types.Tool(
                name="draft_brief",
                description="Draft a short brief.",
                inputSchema={"type": "object", "properties": {}},
            )
        ]
        self.resource_bridge_tool_names: list[str] = []
        self.prompt_bridge_tool_names: list[str] = []
        self.prompts: list[mcp.types.Prompt] = []
        self.server_errlogs: list[str] = []
        self.received_arguments: list[dict[str, str] | None] = []

    @property
    def supports_prompts(self) -> bool:
        return True

    @property
    def supports_resources(self) -> bool:
        return False

    async def connect_to_server(self, config: dict, name: str) -> None:
        _ = config
        self.name = name

    async def list_tools_and_save(self) -> mcp.types.ListToolsResult:
        return mcp.types.ListToolsResult(tools=self.tools)

    async def load_resource_capabilities(self) -> None:
        self.resource_bridge_tool_names = []

    async def load_prompt_capabilities(self) -> None:
        self.prompt_bridge_tool_names = build_mcp_prompt_tool_names(
            self.name or "server"
        )

    async def list_prompts_and_save(
        self,
        cursor: str | None = None,
    ) -> mcp.types.ListPromptsResult:
        _ = cursor
        self.prompts = [
            mcp.types.Prompt(
                name="draft_brief",
                description="Draft a short brief from a topic.",
                arguments=[
                    mcp.types.PromptArgument(
                        name="topic",
                        description="Topic to summarize",
                        required=True,
                    )
                ],
            )
        ]
        return mcp.types.ListPromptsResult(prompts=self.prompts)

    async def get_prompt_with_reconnect(
        self,
        name: str,
        arguments: dict[str, str] | None,
        read_timeout_seconds,
    ) -> mcp.types.GetPromptResult:
        _ = read_timeout_seconds
        self.received_arguments.append(arguments)
        return mcp.types.GetPromptResult(
            description=f"Prompt '{name}' resolved.",
            messages=[
                mcp.types.PromptMessage(
                    role="user",
                    content=mcp.types.TextContent(
                        type="text",
                        text=f"Write a concise brief about {arguments.get('topic', 'the topic') if arguments else 'the topic'}.",
                    ),
                )
            ],
        )

    async def cleanup(self) -> None:
        return None


@pytest.mark.asyncio
async def test_prompt_bridge_tools_are_registered_and_removed(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "astrbot.core.provider.func_tool_manager.MCPClient",
        _FakePromptCapableMCPClient,
    )

    tool_mgr = FunctionToolManager()
    client = await tool_mgr._init_mcp_client(
        "demo-server",
        {"command": "node", "args": ["stdio.js"]},
    )

    tool_names = {tool.name for tool in tool_mgr.func_list}
    assert "draft_brief" in tool_names
    assert "mcp_demo_server_list_prompts" in tool_names
    assert "mcp_demo_server_get_prompt" in tool_names

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
async def test_prompt_listing_tool_returns_text_summary():
    client = _FakePromptCapableMCPClient()
    tool = MCPListPromptsTool(
        mcp_client=client,
        mcp_server_name="demo-server",
    )
    context = ContextWrapper(context=SimpleNamespace())

    result = await tool.call(context)

    assert isinstance(result.content[0], mcp.types.TextContent)
    assert "draft_brief" in result.content[0].text
    assert "topic" in result.content[0].text


@pytest.mark.asyncio
async def test_get_prompt_tool_passes_arguments_and_returns_text_summary():
    client = _FakePromptCapableMCPClient()
    tool = MCPGetPromptTool(
        mcp_client=client,
        mcp_server_name="demo-server",
    )
    context = ContextWrapper(context=SimpleNamespace(), tool_call_timeout=30)

    result = await tool.call(
        context,
        name="draft_brief",
        arguments={"topic": "MCP 最小实现"},
    )

    assert client.received_arguments == [{"topic": "MCP 最小实现"}]
    assert isinstance(result.content[0], mcp.types.TextContent)
    assert "Prompt: draft_brief" in result.content[0].text
    assert "MCP 最小实现" in result.content[0].text


def test_shape_get_prompt_result_summarizes_non_text_blocks():
    result = shape_get_prompt_result(
        server_name="demo-server",
        prompt_name="rich_prompt",
        response=mcp.types.GetPromptResult(
            description="Rich prompt response.",
            messages=[
                mcp.types.PromptMessage(
                    role="assistant",
                    content=mcp.types.ImageContent(
                        type="image",
                        data="ZmFrZQ==",
                        mimeType="image/png",
                    ),
                ),
                mcp.types.PromptMessage(
                    role="user",
                    content=mcp.types.EmbeddedResource(
                        type="resource",
                        resource=mcp.types.TextResourceContents(
                            uri="memo://prompt/context",
                            mimeType="text/plain",
                            text="embedded context",
                        ),
                    ),
                ),
            ],
        ),
    )

    assert "Image block returned." in result
    assert "Embedded text resource returned." in result
    assert "embedded context" in result
