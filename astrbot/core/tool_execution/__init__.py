"""Tool Execution Module

洋葱架构的工具执行模块。
"""

from .interfaces import (
    IMethodResolver,
    IParameterValidator,
    IResultProcessor,
    ITimeoutStrategy,
    ITimeoutHandler,
    IBackgroundTaskManager,
    ICompletionSignal,
    ICallbackEventBuilder,
)

from .errors import (
    ToolExecutionError,
    MethodResolutionError,
    ParameterValidationError,
    TimeoutError,
    BackgroundTaskError,
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
