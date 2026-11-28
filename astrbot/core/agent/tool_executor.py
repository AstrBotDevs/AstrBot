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
    def execute(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[TContext],
        **tool_args,
    ) -> AsyncGenerator[Any | mcp.types.CallToolResult, None]: ...
