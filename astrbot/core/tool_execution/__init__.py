"""Tool Execution Module

洋葱架构的工具执行模块。
"""

from .errors import (
    BackgroundTaskError,
    MethodResolutionError,
    ParameterValidationError,
    TimeoutError,
    ToolExecutionError,
)
from .interfaces import (
    IBackgroundTaskManager,
    ICallbackEventBuilder,
    ICompletionSignal,
    IMethodResolver,
    IParameterValidator,
    IResultProcessor,
    ITimeoutHandler,
    ITimeoutStrategy,
)

__all__ = [
    # Interfaces
    "IMethodResolver",
    "IParameterValidator",
    "IResultProcessor",
    "ITimeoutStrategy",
    "ITimeoutHandler",
    "IBackgroundTaskManager",
    "ICompletionSignal",
    "ICallbackEventBuilder",
    # Errors
    "ToolExecutionError",
    "MethodResolutionError",
    "ParameterValidationError",
    "TimeoutError",
    "BackgroundTaskError",
]
