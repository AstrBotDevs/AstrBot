from typing import Generic

import mcp

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.provider.entities import LLMResponse

from .run_context import ContextWrapper, TContext


class BaseAgentRunHooks(Generic[TContext]):
    async def on_agent_begin(self, run_context: ContextWrapper[TContext]) -> None: ...
    async def on_agent_step_start(self, run_context: ContextWrapper[TContext]) -> None:
        """Run before each model decision and its tools.

        Args:
            run_context: Mutable execution context for the upcoming step.
        """

    async def on_agent_step_end(self, run_context: ContextWrapper[TContext]) -> None:
        """Run after a complete step's tool results and images are assembled.

        Args:
            run_context: Execution context containing the whole completed step.
        """

    async def on_llm_response(
        self,
        run_context: ContextWrapper[TContext],
        llm_response: LLMResponse,
    ) -> None:
        """Handle a final model reply independently from execution cleanup.

        Args:
            run_context: Context associated with the response.
            llm_response: Final model response, available before delivery.
        """

    async def on_tool_start(
        self,
        run_context: ContextWrapper[TContext],
        tool: FunctionTool,
        tool_args: dict | None,
    ) -> None: ...
    async def on_tool_end(
        self,
        run_context: ContextWrapper[TContext],
        tool: FunctionTool,
        tool_args: dict | None,
        tool_result: mcp.types.CallToolResult | None,
    ) -> None: ...
    async def on_agent_done(
        self,
        run_context: ContextWrapper[TContext],
        llm_response: LLMResponse | None,
    ) -> None:
        """Handle execution exit, including failures and cancellation.

        Args:
            run_context: Context with run_end_reason and any run_error populated
                by the built-in tool-loop runner.
            llm_response: Final response, or None if execution produced none.
        """
