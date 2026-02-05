"""回调事件构建器"""

from typing import Any
from astrbot.core.tool_execution.interfaces import ICallbackEventBuilder


class CallbackEventBuilder(ICallbackEventBuilder):
    """回调事件构建器实现"""

    def build(self, task: Any, original_event: Any) -> Any:
        """构建回调事件"""
        from astrbot.core.tool_execution.infrastructure.background import EventFactory

        return EventFactory().build(task, original_event)
