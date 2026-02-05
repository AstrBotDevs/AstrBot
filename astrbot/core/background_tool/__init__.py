# Background Tool Execution System
# 后台工具执行系统

from .task_state import BackgroundTask, TaskStatus
from .task_registry import TaskRegistry
from .output_buffer import OutputBuffer
from .task_executor import TaskExecutor
from .task_notifier import TaskNotifier
from .callback_event_builder import CallbackEventBuilder
from .callback_publisher import CallbackPublisher
from .manager import BackgroundToolManager


class WaitInterruptedException(Exception):
    """等待被新消息中断的异常

    当wait_tool_result被用户新消息中断时抛出此异常，
    用于通知框架结束当前LLM响应周期。
    """

    def __init__(self, task_id: str, session_id: str):
        self.task_id = task_id
        self.session_id = session_id
        super().__init__(f"Wait interrupted for task {task_id}")


__all__ = [
    "BackgroundTask",
    "TaskStatus",
    "TaskRegistry",
    "OutputBuffer",
    "TaskExecutor",
    "TaskNotifier",
    "CallbackEventBuilder",
    "CallbackPublisher",
    "BackgroundToolManager",
    "WaitInterruptedException",
]
