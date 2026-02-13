"""TaskNotifier 单元测试"""

from unittest.mock import AsyncMock

import pytest

from astrbot.core.background_tool.task_notifier import TaskNotifier
from astrbot.core.background_tool.task_state import BackgroundTask


class TestTaskNotifier:
    """测试任务通知器"""

    def setup_method(self):
        """每个测试前初始化"""
        self.notifier = TaskNotifier()

    @pytest.mark.asyncio
    async def test_notify_completion(self):
        """测试通知任务完成"""
        task = BackgroundTask(
            task_id="test-001",
            tool_name="test_tool",
            tool_args={"key": "value"},
            session_id="platform:group:123",
        )
        task.start()
        task.complete("Task completed successfully")

        # 模拟发送消息的回调
        send_callback = AsyncMock()

        await self.notifier.notify_completion(
            task=task,
            send_callback=send_callback,
        )

        # 验证回调被调用
        send_callback.assert_called_once()
        call_args = send_callback.call_args
        message = call_args[0][0]
        assert "test-001" in message
        assert "completed" in message.lower()

    @pytest.mark.asyncio
    async def test_notify_failure(self):
        """测试通知任务失败"""
        task = BackgroundTask(
            task_id="test-002",
            tool_name="test_tool",
            tool_args={},
            session_id="platform:group:123",
        )
        task.start()
        task.fail("Something went wrong")

        send_callback = AsyncMock()

        await self.notifier.notify_completion(
            task=task,
            send_callback=send_callback,
        )

        send_callback.assert_called_once()
        call_args = send_callback.call_args
        message = call_args[0][0]
        assert "failed" in message.lower()

    @pytest.mark.asyncio
    async def test_build_notification_message(self):
        """测试构建通知消息"""
        task = BackgroundTask(
            task_id="test-003",
            tool_name="my_tool",
            tool_args={"param": "value"},
            session_id="platform:group:123",
        )
        task.start()
        task.complete("Result data")

        message = self.notifier.build_message(task)

        assert "test-003" in message
        assert "my_tool" in message
        assert "Result data" in message

    def test_should_notify(self):
        """测试是否应该通知"""
        # 完成的任务应该通知
        task1 = BackgroundTask(
            task_id="test-004",
            tool_name="tool",
            tool_args={},
            session_id="session",
        )
        task1.start()
        task1.complete("done")
        assert self.notifier.should_notify(task1)

        # 运行中的任务不应该通知
        task2 = BackgroundTask(
            task_id="test-005",
            tool_name="tool",
            tool_args={},
            session_id="session",
        )
        task2.start()
        assert not self.notifier.should_notify(task2)
