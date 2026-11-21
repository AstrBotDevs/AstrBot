import asyncio
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from typing import Any, Generic

import mcp

from .run_context import ContextWrapper, TContext
from .tool import FunctionTool

# ID of the tool call being executed, set by the runner around execute() so
# executors can refer to the call (e.g. an approval prompt for it).
CURRENT_TOOL_CALL_ID: ContextVar[str | None] = ContextVar(
    "current_tool_call_id", default=None
)


class BaseFunctionToolExecutor(Generic[TContext]):
    @classmethod
    def detach(
        cls,
        *,
        tool: FunctionTool,
        run_context: ContextWrapper[TContext],
        executor: AsyncGenerator,
        pending_result: asyncio.Task,
        task_id: str,
        arguments: dict,
    ) -> mcp.types.CallToolResult | None:
        """Optionally take ownership of an executing tool without restarting it.

        Args:
            tool: Tool already executing.
            run_context: Context of the initiating turn.
            executor: Iterator to continue and close after the pending read.
            pending_result: In-flight read that must not be restarted or cancelled.
            task_id: Execution identity used to correlate the eventual result.
            arguments: Actual tool arguments, for completion reporting.

        Returns:
            A foreground handoff result if ownership was accepted, otherwise None.
        """
        return None

    @classmethod
    def execute(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[TContext],
        **tool_args,
    ) -> AsyncGenerator[Any | mcp.types.CallToolResult, None]: ...
