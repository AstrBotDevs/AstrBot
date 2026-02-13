"""LLM工具集单元测试"""

import asyncio
from unittest.mock import MagicMock

import pytest

from astrbot.core.background_tool.llm_tools import (
    get_tool_output,
    list_running_tools,
    stop_tool,
)
from astrbot.core.background_tool.manager import BackgroundToolManager
from astrbot.core.background_tool.task_state import BackgroundTask


class TestLLMTools:
    """测试LLM工具集"""

    def setup_method(self):
        """每个测试前初始化"""
        self.manager = BackgroundToolManager()
        self.manager.registry.clear()

    @pytest.mark.asyncio
    async def test_get_tool_output(self):
        """测试获取工具输出"""
        # 创建一个任务并添加输出
        task = BackgroundTask(
            task_id="test-001",
            tool_name="test_tool",
            tool_args={},
            session_id="session-A",
        )
        self.manager.registry.register(task)
        self.manager.output_buffer.append("test-001", "line 1")
        self.manager.output_buffer.append("test-001", "line 2")

        # 模拟事件对象
        mock_event = MagicMock()
        mock_event.unified_msg_origin = "session-A"

        result = await get_tool_output(mock_event, task_id="test-001")

        assert "line 1" in result
        assert "line 2" in result

    @pytest.mark.asyncio
    async def test_get_tool_output_not_found(self):
        """测试获取不存在的任务输出"""
        mock_event = MagicMock()
        mock_event.unified_msg_origin = "session-A"

        result = await get_tool_output(mock_event, task_id="nonexistent")

        assert "not found" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_stop_tool(self):
        """测试停止工具"""

        async def slow_handler(**kwargs):
            await asyncio.sleep(10)
            return "done"

        task_id = await self.manager.submit_task(
            tool_name="slow_tool",
            tool_args={},
            session_id="session-A",
            handler=slow_handler,
            wait=False,
        )

        await asyncio.sleep(0.1)

        mock_event = MagicMock()
        mock_event.unified_msg_origin = "session-A"

        result = await stop_tool(mock_event, task_id=task_id)

        assert "stopped" in result.lower() or "cancelled" in result.lower()

    @pytest.mark.asyncio
    async def test_list_running_tools(self):
        """测试列出运行中的工具"""

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

        mock_event = MagicMock()
        mock_event.unified_msg_origin = "session-A"

        result = await list_running_tools(mock_event)

        # 清理
        await self.manager.stop_task(task_id)

        # 结果应该是字符串
        assert isinstance(result, str)
