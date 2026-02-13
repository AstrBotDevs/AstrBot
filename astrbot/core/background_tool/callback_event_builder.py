"""回调事件构建器

将后台任务完成信息构建为可放入事件队列的回调事件。
遵循单一职责原则，只负责事件构建。
"""

import copy
import time
from typing import Any

from astrbot import logger
from astrbot.core.tool_execution.domain.config import DEFAULT_CONFIG

from .task_state import BackgroundTask, TaskStatus

# 状态文本映射
STATUS_TEXT_MAP = {
    TaskStatus.COMPLETED: "completed successfully",
    TaskStatus.FAILED: "failed",
    TaskStatus.CANCELLED: "was cancelled",
}


class CallbackEventBuilder:
    """回调事件构建器

    负责将后台任务构建为回调事件，不涉及队列操作。
    """

    def __init__(self, config=None):
        """初始化构建器

        Args:
            config: 配置对象，默认使用 DEFAULT_CONFIG
        """
        self._config = config or DEFAULT_CONFIG

    def build_notification_text(self, task: BackgroundTask) -> str:
        """构建通知文本

        Args:
            task: 后台任务

        Returns:
            通知文本
        """
        status = STATUS_TEXT_MAP.get(task.status, "unknown")

        lines = [
            "[Background Task Callback]",
            f"Task ID: {task.task_id}",
            f"Tool: {task.tool_name}",
            f"Status: {status}",
        ]

        if task.result:
            lines.append(f"Result: {task.result}")

        if task.error:
            max_len = self._config.error_preview_max_length
            error_preview = task.error[:max_len]
            if len(task.error) > max_len:
                error_preview += "..."
            lines.append(f"Error: {error_preview}")

        lines.append("")
        lines.append(
            "Please inform the user about this task completion and provide any relevant details."
        )

        return "\n".join(lines)

    def build_message_object(self, task: BackgroundTask, text: str) -> Any:
        """构建消息对象

        Args:
            task: 后台任务
            text: 通知文本

        Returns:
            AstrBotMessage 对象
        """
        from astrbot.core.message.components import Plain
        from astrbot.core.platform.astrbot_message import AstrBotMessage

        original = task.event.message_obj

        msg = AstrBotMessage()
        msg.type = original.type
        msg.self_id = original.self_id
        msg.session_id = original.session_id
        msg.message_id = f"bg_task_{task.task_id}"
        msg.group = original.group
        msg.sender = original.sender
        msg.message = [Plain(text)]
        msg.message_str = text
        msg.raw_message = None
        msg.timestamp = int(time.time())

        return msg

    def build_callback_event(self, task: BackgroundTask) -> Any | None:
        """构建完整的回调事件

        Args:
            task: 后台任务

        Returns:
            回调事件对象，构建失败返回 None
        """
        if not task.event:
            logger.warning(f"[CallbackEventBuilder] Task {task.task_id} has no event")
            return None

        try:
            from astrbot.core.utils.trace import TraceSpan

            text = self.build_notification_text(task)
            msg_obj = self.build_message_object(task, text)

            # 浅拷贝原事件，保留平台特定属性
            new_event = copy.copy(task.event)
            new_event.message_str = text
            new_event.message_obj = msg_obj

            # 重置状态
            new_event._result = None
            new_event._has_send_oper = False
            new_event._extras = {}

            # 初始化 trace
            new_event.trace = TraceSpan(
                name="BackgroundTaskCallback",
                umo=new_event.unified_msg_origin,
                sender_name=new_event.get_sender_name(),
                message_outline=f"[Background Task {task.task_id}]",
            )
            new_event.span = new_event.trace

            # 标记为回调事件
            new_event.is_wake = True
            new_event.is_at_or_wake_command = True
            new_event.set_extra("is_background_task_callback", True)
            new_event.set_extra("background_task_id", task.task_id)

            return new_event

        except Exception as e:
            logger.error(
                f"[CallbackEventBuilder] Failed to build event for task {task.task_id}: {e}"
            )
            return None
