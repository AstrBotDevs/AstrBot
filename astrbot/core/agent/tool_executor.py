from collections.abc import AsyncGenerator
from typing import Any, Generic
import abc

import mcp

from .run_context import ContextWrapper, TContext
from .tool import FunctionTool


class BaseFunctionToolExecutor(abc.ABC, Generic[TContext]):
    @classmethod
    @abc.abstractmethod
    async def execute(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[TContext],
        **tool_args,
    ) -> AsyncGenerator[Any | mcp.types.CallToolResult, None]: ...
