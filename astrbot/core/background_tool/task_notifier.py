"""任务通知器

任务完成后主动通知AI。
"""

from typing import Callable, Awaitable

from .task_state import BackgroundTask, TaskStatus


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

    def build_message(self, task: BackgroundTask) -> str:
        """构建通知消息

        Args:
            task: 后台任务

        Returns:
            通知消息文本
        """
        status_text = {
            TaskStatus.COMPLETED: "completed successfully",
            TaskStatus.FAILED: "failed",
            TaskStatus.CANCELLED: "was cancelled",
        }.get(task.status, "finished")

        lines = [
            f"[Background Task Notification]",
            f"Task ID: {task.task_id}",
            f"Tool: {task.tool_name}",
            f"Status: {status_text}",
        ]

        if task.result:
            lines.append(f"Result: {task.result}")

        if task.error:
            lines.append(f"Error: {task.error}")

        return "\n".join(lines)

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
