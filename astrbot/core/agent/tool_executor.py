from collections.abc import AsyncGenerator
from typing import Any, Generic

import mcp

from .run_context import ContextWrapper, TContext
from .tool import FunctionTool, ToolSet


class BaseFunctionToolExecutor(Generic[TContext]):
    @classmethod
    def prepare_tools(
        cls, tools: ToolSet, run_context: ContextWrapper[TContext]
    ) -> ToolSet:
        """Bind host execution policies to the catalog before discovery."""
        return tools

    @classmethod
    def execute(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[TContext],
        **tool_args,
    ) -> AsyncGenerator[Any | mcp.types.CallToolResult, None]: ...
