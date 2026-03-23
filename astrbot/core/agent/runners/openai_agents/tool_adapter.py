"""Adapter to convert AstrBot FunctionTool to openai-agents FunctionTool.

This module provides utilities to convert between AstrBot's tool representation
and the openai-agents library's FunctionTool format.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agents import FunctionTool as AgentsFunctionTool
from agents.tool import ToolContext

from astrbot.core.agent.tool import FunctionTool


def create_agents_tool(
    name: str,
    description: str,
    params_json_schema: dict[str, Any],
    on_invoke_tool: Callable[[ToolContext[Any], str], Awaitable[Any]],
) -> AgentsFunctionTool:
    """Create an openai-agents FunctionTool from a handler function.

    This is a helper to create tools that integrate with the openai-agents SDK.
    """
    return AgentsFunctionTool(
        name=name,
        description=description,
        params_json_schema=params_json_schema,
        on_invoke_tool=on_invoke_tool,
    )


def astrbot_tool_to_agents_tool(
    tool: FunctionTool,
    handler: Callable[..., Awaitable[Any]],
) -> AgentsFunctionTool:
    """Convert an AstrBot FunctionTool to an openai-agents FunctionTool.

    Args:
        tool: The AstrBot FunctionTool to convert
        handler: The async function to call when the tool is invoked.
                  Should have the signature: async def handler(tool_context, tool_name) -> Any

    Returns:
        An openai-agents FunctionTool that wraps the AstrBot tool
    """

    async def wrapper(tool_context: ToolContext[Any], tool_name: str) -> Any:
        return await handler(tool.context, tool.name)

    return AgentsFunctionTool(
        name=tool.name,
        description=tool.desc,
        params_json_schema=tool.parameters,
        on_invoke_tool=wrapper,
    )
