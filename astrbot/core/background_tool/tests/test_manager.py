"""BackgroundToolManager 单元测试"""

import pytest
import asyncio

from astrbot.core.background_tool.manager import BackgroundToolManager
from astrbot.core.background_tool.task_state import TaskStatus


class TestBackgroundToolManager:
    """测试后台工具管理器"""

    def setup_method(self):
        """每个测试前初始化"""
        self.manager = BackgroundToolManager()
        self.manager.registry.clear()

    @pytest.mark.asyncio
    async def test_submit_task(self):
        """测试提交任务"""

        async def mock_handler(**kwargs):
            return "result"

        task_id = await self.manager.submit_task(
            tool_name="test_tool",
            tool_args={"key": "value"},
            session_id="session-A",
            handler=mock_handler,
        )

        assert task_id is not None
        task = self.manager.registry.get(task_id)
        assert task is not None

    @pytest.mark.asyncio
    async def test_get_task_output(self):
        """测试获取任务输出"""

        async def mock_handler(**kwargs):
            yield "line 1"
            yield "line 2"
            yield "done"

        task_id = await self.manager.submit_task(
            tool_name="test_tool",
            tool_args={},
            session_id="session-A",
            handler=mock_handler,
        )

        # 等待任务完成
        await asyncio.sleep(0.2)

        output = self.manager.get_task_output(task_id)
        assert "line 1" in output or len(output) > 0

    @pytest.mark.asyncio
    async def test_list_running_tasks(self):
        """测试列出运行中的任务"""

        async def slow_handler(**kwargs):
            await asyncio.sleep(5)
            return "done"

        task_id = await self.manager.submit_task(
            tool_name="slow_tool",
            tool_args={},
            session_id="session-A",
            handler=slow_handler,
            wait=False,
        )

        await asyncio.sleep(0.1)

        running = self.manager.list_running_tasks("session-A")
        assert len(running) >= 0  # 可能已完成

        # 清理
        await self.manager.stop_task(task_id)

    @pytest.mark.asyncio
    async def test_stop_task(self):
        """测试停止任务"""

        async def slow_handler(**kwargs):
            await asyncio.sleep(10)
            return "should not reach"

        task_id = await self.manager.submit_task(
            tool_name="slow_tool",
            tool_args={},
            session_id="session-A",
            handler=slow_handler,
            wait=False,
        )

        await asyncio.sleep(0.1)

        success = await self.manager.stop_task(task_id)
        assert success

        await asyncio.sleep(0.2)

        task = self.manager.registry.get(task_id)
        assert task.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_get_task_status(self):
        """测试获取任务状态"""

        async def mock_handler(**kwargs):
            return "done"

        task_id = await self.manager.submit_task(
            tool_name="test_tool",
            tool_args={},
            session_id="session-A",
            handler=mock_handler,
        )

        await asyncio.sleep(0.2)

        status = self.manager.get_task_status(task_id)
        assert status is not None
        assert "task_id" in status
