from collections.abc import AsyncGenerator
from typing import Generic

import mcp

from .run_context import ContextWrapper, TContext
from .tool import FunctionTool

# 子类工具执行器的统一返回类型（yield 值）
ToolExecResult = mcp.types.CallToolResult | str | None


class BaseFunctionToolExecutor(Generic[TContext]):
    @classmethod
    async def execute(
        cls,
        tool: FunctionTool[TContext],
        run_context: ContextWrapper[TContext],
        **tool_args: object,
    ) -> AsyncGenerator[ToolExecResult, None]: ...
