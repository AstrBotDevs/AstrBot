"""后台工具管理器

编排所有模块，提供统一接口。
"""

import asyncio
from typing import Any, Callable, Awaitable, AsyncGenerator

from .task_state import BackgroundTask, TaskStatus
from .task_registry import TaskRegistry
from .task_executor import TaskExecutor
from .task_notifier import TaskNotifier
from .output_buffer import OutputBuffer


class BackgroundToolManager:
    """后台工具管理器

    核心编排器，管理后台任务的完整生命周期。
    """

    _instance = None

    # 清理配置
    CLEANUP_INTERVAL_SECONDS = 600  # 每10分钟清理一次
    TASK_MAX_AGE_SECONDS = 3600  # 已完成任务保留1小时

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.registry = TaskRegistry()
        self.output_buffer = OutputBuffer()
        self.executor = TaskExecutor(output_buffer=self.output_buffer)
        self.notifier = TaskNotifier()
        self._interrupt_flags = {}  # session_id -> bool，用于中断等待
        self._cleanup_task: asyncio.Task | None = None
        self._initialized = True

    def start_cleanup_task(self) -> None:
        """启动定时清理任务

        应在事件循环启动后调用。如果事件循环未运行，则跳过。
        """
        if self._cleanup_task is None or self._cleanup_task.done():
            try:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            except RuntimeError:
                # 事件循环未运行，跳过
                pass

    async def _cleanup_loop(self) -> None:
        """定时清理已完成任务的循环"""
        from astrbot import logger

        logger.info("[BackgroundToolManager] Cleanup task started")

        while True:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL_SECONDS)

                removed_count = self.registry.cleanup_finished_tasks(
                    max_age_seconds=self.TASK_MAX_AGE_SECONDS
                )

                if removed_count > 0:
                    stats = self.registry.count_by_status()
                    logger.info(
                        f"[BackgroundToolManager] Cleaned up {removed_count} finished tasks, "
                        f"remaining: {self.registry.count()} tasks ({stats})"
                    )
            except asyncio.CancelledError:
                logger.info("[BackgroundToolManager] Cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"[BackgroundToolManager] Cleanup error: {e}")

    def stop_cleanup_task(self) -> None:
        """停止定时清理任务"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

    async def submit_task(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        session_id: str,
        handler: Callable[..., Awaitable[str] | AsyncGenerator[str, None]],
        wait: bool = True,
        event: Any = None,
        event_queue: Any = None,
    ) -> str:
        """提交后台任务

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            session_id: 会话ID
            handler: 工具处理函数
            wait: 是否等待完成
            event: 原始事件对象（用于后台执行）
            event_queue: 事件队列（用于触发AI回调）

        Returns:
            任务ID
        """
        # 延迟启动清理任务（确保事件循环已运行）
        self.start_cleanup_task()

        task = BackgroundTask(
            task_id=BackgroundTask.generate_id(),
            tool_name=tool_name,
            tool_args=tool_args,
            session_id=session_id,
            event=event,
            event_queue=event_queue,
        )
        task.init_completion_event()

        from astrbot import logger

        logger.info(
            f"[BackgroundToolManager] Creating task {task.task_id} for tool {tool_name}, session {session_id}"
        )

        task.init_completion_event()
        self.registry.register(task)
        logger.info(
            f"[BackgroundToolManager] Task {task.task_id} registered successfully"
        )

        if wait:
            await self.executor.execute(task=task, handler=handler)
        else:
            asyncio.create_task(self.executor.execute(task=task, handler=handler))

        return task.task_id

    def get_task_output(self, task_id: str, lines: int = 50) -> str:
        """获取任务输出

        Args:
            task_id: 任务ID
            lines: 返回最近N行

        Returns:
            输出日志文本
        """
        output_lines = self.output_buffer.get_recent(task_id, n=lines)
        return "\n".join(output_lines)

    async def wait_task_result(
        self,
        task_id: str,
        timeout: float = 300,
    ) -> str | None:
        """等待任务结果

        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）

        Returns:
            任务结果，超时返回None
        """
        task = self.registry.get(task_id)
        if task is None:
            return None

        start_time = asyncio.get_event_loop().time()
        while not task.is_finished():
            if asyncio.get_event_loop().time() - start_time > timeout:
                return None
            await asyncio.sleep(0.5)

        return task.result

    async def stop_task(self, task_id: str) -> bool:
        """停止任务

        Args:
            task_id: 任务ID

        Returns:
            是否停止成功
        """
        return await self.executor.cancel(task_id)

    def list_running_tasks(self, session_id: str) -> list[dict[str, Any]]:
        """列出运行中的任务

        Args:
            session_id: 会话ID

        Returns:
            运行中的任务列表
        """
        tasks = self.registry.get_running_tasks(session_id)
        return [t.to_dict() for t in tasks]

    def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态字典
        """
        task = self.registry.get(task_id)
        if task is None:
            return None
        return task.to_dict()

    def get_pending_notifications(self, session_id: str) -> list[dict[str, Any]]:
        """获取待发送的通知

        Args:
            session_id: 会话ID

        Returns:
            待发送通知列表，每项包含task_id和message
        """
        tasks = self.registry.get_by_session(session_id)
        pending = []
        for task in tasks:
            if task.notification_message and not task.notification_sent:
                pending.append(
                    {
                        "task_id": task.task_id,
                        "tool_name": task.tool_name,
                        "status": task.status.value,
                        "message": task.notification_message,
                    }
                )
        return pending

    def mark_notification_sent(self, task_id: str) -> bool:
        """标记通知已发送

        Args:
            task_id: 任务ID

        Returns:
            是否标记成功
        """
        task = self.registry.get(task_id)
        if task is None:
            return False
        task.notification_sent = True
        return True

    def set_interrupt_flag(self, session_id: str):
        """设置会话的中断标记（用于打断wait_tool_result）

        Args:
            session_id: 会话ID
        """
        self._interrupt_flags[session_id] = True

    def check_interrupt_flag(self, session_id: str) -> bool:
        """检查会话是否有中断标记

        Args:
            session_id: 会话ID

        Returns:
            是否有中断标记
        """
        return self._interrupt_flags.get(session_id, False)

    def clear_interrupt_flag(self, session_id: str):
        """清除会话的中断标记

        Args:
            session_id: 会话ID
        """
        self._interrupt_flags.pop(session_id, None)

    def get_running_tasks_status(self, session_id: str) -> str | None:
        """获取会话中正在运行的后台任务状态信息

        Args:
            session_id: 会话ID

        Returns:
            后台任务状态信息，如果没有运行中的任务则返回None
        """
        running_tasks = self.list_running_tasks(session_id)
        if not running_tasks:
            return None

        status_lines = ["[Background Tasks Status]"]
        for task in running_tasks:
            status_lines.append(
                f"- Task {task['task_id']}: {task['tool_name']} ({task['status']})"
            )
        status_lines.append(
            "Note: These tasks are running in the background and will notify you when complete."
        )

        return "\n".join(status_lines)
