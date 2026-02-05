"""Domain Layer

领域层，定义核心类型，无外部依赖。
"""

from .tool_types import ToolType, ExecutionMode
from .execution_result import ExecutionResult, ExecutionStatus

__all__ = [
    "ToolType",
    "ExecutionMode",
    "ExecutionResult",
    "ExecutionStatus",
]
