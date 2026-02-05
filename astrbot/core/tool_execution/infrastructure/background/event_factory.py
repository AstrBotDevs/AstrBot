"""事件工厂

构建回调事件。
"""

import copy
import time
from typing import Any

from astrbot.core.tool_execution.interfaces import ICallbackEventBuilder


class EventFactory(ICallbackEventBuilder):
    """事件工厂实现"""
    
    def build(self, task: Any, original_event: Any) -> Any:
        """构建回调事件"""
        if not original_event:
            return None
        
        notification = self._build_notification(task)
        return self._create_event(original_event, task, notification)

    
    def _build_notification(self, task: Any) -> str:
        """构建通知消息"""
        status = self._get_status_text(task.status)
        msg = f"[Background Task]\nID: {task.task_id}\nTool: {task.tool_name}\nStatus: {status}"
        if task.result:
            msg += f"\nResult: {task.result}"
        return msg

    
    def _get_status_text(self, status) -> str:
        """获取状态文本"""
        from astrbot.core.background_tool import TaskStatus
        mapping = {
            TaskStatus.COMPLETED: "completed",
            TaskStatus.FAILED: "failed",
            TaskStatus.CANCELLED: "cancelled",
        }
        return mapping.get(status, "unknown")

    
    def _create_event(self, original: Any, task: Any, msg: str) -> Any:
        """创建新事件"""
        new_event = copy.copy(original)
        new_event.message_str = msg
        new_event.is_wake = True
        new_event.set_extra("is_background_task_callback", True)
        new_event.set_extra("background_task_id", task.task_id)
        return new_event
