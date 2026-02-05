"""领域错误类型

定义工具执行相关的错误类型。
"""


class ToolExecutionError(Exception):
    """工具执行基础错误"""

    pass


class MethodResolutionError(ToolExecutionError):
    """方法解析错误"""

    pass


class ParameterValidationError(ToolExecutionError):
    """参数验证错误"""

    pass


class TimeoutError(ToolExecutionError):
    """超时错误"""

    pass


class BackgroundTaskError(ToolExecutionError):
    """后台任务错误"""

    pass
