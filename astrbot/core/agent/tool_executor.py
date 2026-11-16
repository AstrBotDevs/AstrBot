from collections.abc import AsyncGenerator
from typing import Any, Generic

import mcp

from .run_context import ContextWrapper, TContext
from .tool import FunctionTool


class BaseFunctionToolExecutor(Generic[TContext]):
    @classmethod
    def execute(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[TContext],
        **tool_args,
    ) -> AsyncGenerator[Any | mcp.types.CallToolResult, None]: ...

    @classmethod
    def execute_with_args(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[TContext],
        tool_args: dict[str, Any],
    ) -> AsyncGenerator[Any | mcp.types.CallToolResult, None]:
        """Execute a tool with its arguments kept separate from executor controls.

        This fallback preserves compatibility for existing executor subclasses.
        Executors that support arguments matching their control parameter names
        should override this method and pass the mapping through without expansion.
        """
        return cls.execute(tool, run_context, **tool_args)
