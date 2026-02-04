"""TaskExecutor 单元测试"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from astrbot.core.background_tool.task_state import BackgroundTask, TaskStatus
from astrbot.core.background_tool.task_executor import TaskExecutor
from astrbot.core.background_tool.output_buffer import OutputBuffer


class TestTaskExecutor:
    """测试任务执行器"""

    def setup_method(self):
        """每个测试前初始化"""
        self.output_buffer = OutputBuffer()
        self.executor = TaskExecutor(output_buffer=self.output_buffer)

    @pytest.mark.asyncio
    async def test_execute_simple_task(self):
        """测试执行简单任务"""
        task = BackgroundTask(
            task_id="test-001",
            tool_name="test_tool",
            tool_args={"param": "value"},
            session_id="session-A",
        )

        # 模拟工具处理函数
        async def mock_handler(**kwargs):
            return "success result"

        result = await self.executor.execute(
            task=task,
            handler=mock_handler,
        )

        assert task.status == TaskStatus.COMPLETED
        assert task.result == "success result"

    @pytest.mark.asyncio
    async def test_execute_with_output(self):
        """测试执行带输出的任务"""
        task = BackgroundTask(
            task_id="test-002",
            tool_name="test_tool",
            tool_args={},
            session_id="session-A",
        )

        async def mock_handler(**kwargs):
            # 模拟输出
            yield "Processing step 1..."
            yield "Processing step 2..."
            yield "done"

        await self.executor.execute(
            task=task,
            handler=mock_handler,
        )

        # 检查输出缓冲区
        lines = self.output_buffer.get_all("test-002")
        assert len(lines) >= 2

    @pytest.mark.asyncio
    async def test_execute_failed_task(self):
        """测试执行失败的任务"""
        task = BackgroundTask(
            task_id="test-003",
            tool_name="test_tool",
            tool_args={},
            session_id="session-A",
        )

        async def mock_handler(**kwargs):
            raise Exception("Test error")

        await self.executor.execute(
            task=task,
            handler=mock_handler,
        )

        assert task.status == TaskStatus.FAILED
        assert "Test error" in task.error

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        """测试取消任务"""
        task = BackgroundTask(
            task_id="test-004",
            tool_name="test_tool",
            tool_args={},
            session_id="session-A",
        )

        async def slow_handler(**kwargs):
            await asyncio.sleep(10)
            return "should not reach"

        # 启动任务
        exec_task = asyncio.create_task(
            self.executor.execute(task=task, handler=slow_handler)
        )

        # 等待任务开始
        await asyncio.sleep(0.1)

        # 取消任务
        success = await self.executor.cancel("test-004")

        # 等待任务完成
        await asyncio.sleep(0.2)

        assert success
        assert task.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_is_running(self):
        """测试检查任务是否运行中"""
        task = BackgroundTask(
            task_id="test-005",
            tool_name="test_tool",
            tool_args={},
            session_id="session-A",
        )

        async def slow_handler(**kwargs):
            await asyncio.sleep(1)
            return "done"

        # 启动任务
        exec_task = asyncio.create_task(
            self.executor.execute(task=task, handler=slow_handler)
        )

        await asyncio.sleep(0.1)

        assert self.executor.is_running("test-005")

        # 取消并等待
        await self.executor.cancel("test-005")
        await asyncio.sleep(0.1)

        assert not self.executor.is_running("test-005")
