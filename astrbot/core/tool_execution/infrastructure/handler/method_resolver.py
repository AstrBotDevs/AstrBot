"""方法解析器

从工具对象中解析出可调用的方法。
"""

from typing import Any, Callable

from astrbot.core.tool_execution.interfaces import IMethodResolver
from astrbot.core.tool_execution.errors import MethodResolutionError


class MethodResolver(IMethodResolver):
    """方法解析器实现"""
    
    def resolve(self, tool: Any) -> tuple[Callable, str]:
        """解析工具的可调用方法"""
        # 检查是否重写了call方法
        is_override_call = self._check_override_call(tool)
        
        # 按优先级解析方法
        if tool.handler:
            return tool.handler, "decorator_handler"
        elif is_override_call:
            return tool.call, "call"
        elif hasattr(tool, "run"):
            return getattr(tool, "run"), "run"
        
        raise MethodResolutionError(
            "Tool must have a valid handler or override 'run' method."
        )

    
    def _check_override_call(self, tool: Any) -> bool:
        """检查工具是否重写了call方法"""
        from astrbot.core.agent.tool import FunctionTool
        
        for ty in type(tool).mro():
            if "call" in ty.__dict__:
                if ty.__dict__["call"] is not FunctionTool.call:
                    return True
        return False
