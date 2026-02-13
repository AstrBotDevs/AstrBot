"""回调事件发布器

负责将回调事件发布到事件队列。
遵循单一职责原则，只负责队列操作。
"""

from astrbot import logger

from .callback_event_builder import CallbackEventBuilder
from .task_state import BackgroundTask


class CallbackPublisher:
    """回调事件发布器

    负责验证条件并将回调事件发布到队列。
    """

    def __init__(self, event_builder: CallbackEventBuilder | None = None):
        """初始化发布器

        Args:
            event_builder: 事件构建器，默认创建新实例
        """
        self._event_builder = event_builder or CallbackEventBuilder()

    def should_publish(self, task: BackgroundTask) -> bool:
        """检查是否应该发布回调

        Args:
            task: 后台任务

        Returns:
            是否应该发布
        """
        if task.is_being_waited:
            logger.info(
                f"[CallbackPublisher] Task {task.task_id} is being waited, skip"
            )
            return False

        if not task.event:
            logger.warning(f"[CallbackPublisher] Task {task.task_id} has no event")
            return False

        if not task.event_queue:
            logger.warning(
                f"[CallbackPublisher] Task {task.task_id} has no event_queue"
            )
            return False

        if not task.notification_message:
            logger.warning(
                f"[CallbackPublisher] Task {task.task_id} has no notification"
            )
            return False

        return True

    async def publish(self, task: BackgroundTask) -> bool:
        """发布回调事件

        Args:
            task: 后台任务

        Returns:
            是否发布成功
        """
        if not self.should_publish(task):
            return False

        try:
            event = self._event_builder.build_callback_event(task)
            if event is None:
                return False

            task.event_queue.put_nowait(event)
            task.notification_sent = True

            logger.info(f"[CallbackPublisher] Task {task.task_id} callback queued")
            return True

        except Exception as e:
            logger.error(f"[CallbackPublisher] Failed to publish callback: {e}")
            return False
