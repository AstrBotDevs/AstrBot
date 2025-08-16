import mcp
from dataclasses import dataclass
from .run_context import ContextWrapper, TContext
from typing import Generic
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.agent.tool import FunctionTool


@dataclass
class BaseAgentRunHooks(Generic[TContext]):
    async def on_agent_begin(self, run_context: ContextWrapper[TContext]): ...
    async def on_tool_start(
        self,
        run_context: ContextWrapper[TContext],
        tool: FunctionTool,
        tool_args: dict | None,
    ): ...
    async def on_tool_end(
        self,
        run_context: ContextWrapper[TContext],
        tool: FunctionTool,
        tool_args: dict | None,
        tool_result: mcp.types.CallToolResult | None,
    ): ...
    async def on_agent_done(
        self, run_context: ContextWrapper[TContext], llm_response: LLMResponse
    ): ...
