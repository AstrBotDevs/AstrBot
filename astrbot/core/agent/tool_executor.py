from collections.abc import AsyncGenerator
from typing import Any

import mcp

from .run_context import ContextWrapper
from .tool import FunctionTool


class BaseFunctionToolExecutor[TContext]:
    @classmethod
    async def execute(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[TContext],
        **tool_args,
    ) -> AsyncGenerator[Any | mcp.types.CallToolResult, None]: ...
