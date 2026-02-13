"""任务通知器

任务完成后主动通知AI。
"""

from collections.abc import Awaitable, Callable

from .task_formatter import build_task_result
from .task_state import BackgroundTask


class TaskNotifier:
    """任务通知器

    负责在后台任务完成后构建通知消息并发送。
    """

    def should_notify(self, task: BackgroundTask) -> bool:
        """检查是否应该通知

        Args:
            task: 后台任务

        Returns:
            是否应该通知
        """
        return task.is_finished()

    def build_message(self, task: BackgroundTask, output: str | None = None) -> str:
        """构建通知消息

        Args:
            task: 后台任务
            output: 输出日志（可选）

        Returns:
            通知消息文本，包含完整的任务信息（状态、输出日志、结果、错误）
        """
        return build_task_result(task.task_id, task, output)

    async def notify_completion(
        self,
        task: BackgroundTask,
        send_callback: Callable[[str], Awaitable[None]],
    ) -> None:
        """通知任务完成

        Args:
            task: 后台任务
            send_callback: 发送消息的回调函数
        """
        if not self.should_notify(task):
            return

        message = self.build_message(task)
        await send_callback(message)
