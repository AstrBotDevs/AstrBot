import mcp
from typing import Any, Generic

from collections.abc import AsyncGenerator
from .run_context import TContext, ContextWrapper
from .tool import FunctionTool


class BaseFunctionToolExecutor(Generic[TContext]):
    @classmethod
    async def execute(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[TContext],
        **tool_args: Any,  # noqa: ANN401
    ) -> AsyncGenerator[Any | mcp.types.CallToolResult, None]: ...
