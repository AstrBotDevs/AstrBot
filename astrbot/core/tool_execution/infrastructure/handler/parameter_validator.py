"""参数验证器

验证工具调用参数。
"""

import inspect
from collections.abc import Callable

from astrbot.core.tool_execution.errors import ParameterValidationError
from astrbot.core.tool_execution.interfaces import IParameterValidator


class ParameterValidator(IParameterValidator):
    """参数验证器实现"""

    def validate(self, handler: Callable, params: dict) -> dict:
        """验证参数"""
        try:
            sig = inspect.signature(handler)
            # 跳过第一个参数（event或context）
            bound = sig.bind_partial(None, **params)
            return dict(bound.arguments)
        except TypeError as e:
            raise ParameterValidationError(self._build_error_message(handler, e))

    def _build_error_message(self, handler: Callable, error: Exception) -> str:
        """构建错误消息"""
        try:
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())[1:]  # 跳过第一个参数
            param_strs = [self._format_param(p) for p in params]
            return f"Parameter mismatch: {', '.join(param_strs)}"
        except Exception:
            return str(error)

    def _format_param(self, param: inspect.Parameter) -> str:
        """格式化参数"""
        s = param.name
        if param.annotation != inspect.Parameter.empty:
            s += f": {param.annotation}"
        return s
