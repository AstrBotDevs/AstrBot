"""工具调用器

包装LLM工具调用逻辑，实现IToolInvoker接口。
"""

from collections.abc import Callable
from typing import Any

from astrbot.core.tool_execution.interfaces import IToolInvoker


class LLMToolInvoker(IToolInvoker):
    """LLM工具调用器

    包装 call_local_llm_tool，隔离应用层与具体实现的依赖。
    """

    def invoke(
        self, context: Any, handler: Callable, method_name: str, **kwargs
    ) -> Any:
        """调用工具

        Args:
            context: 运行上下文
            handler: 处理函数
            method_name: 方法名称
            **kwargs: 工具参数

        Returns:
            异步生成器
        """
        from astrbot.core.astr_agent_tool_exec import call_local_llm_tool

        return call_local_llm_tool(
            context=context,
            handler=handler,
            method_name=method_name,
            **kwargs,
        )
