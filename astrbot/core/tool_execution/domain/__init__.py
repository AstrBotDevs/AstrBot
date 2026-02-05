"""Domain Layer

领域层，定义核心类型，无外部依赖。
"""

from .execution_result import ExecutionResult, ExecutionStatus
from .tool_types import ExecutionMode, ToolType

__all__ = [
    "ToolType",
    "ExecutionMode",
    "ExecutionResult",
    "ExecutionStatus",
]
