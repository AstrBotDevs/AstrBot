from collections.abc import AsyncGenerator
from typing import Any, Generic

import mcp

from .run_context import ContextWrapper, TContext
from .tool import FunctionTool


class BaseFunctionToolExecutor(Generic[TContext]):
    @classmethod
    async def execute(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[TContext],
        **tool_args,
    ) -> AsyncGenerator[Any | mcp.types.CallToolResult, None]: ...
