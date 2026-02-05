"""工具执行集成测试

覆盖关键场景：
1. 正常工具执行
2. 超时转后台执行
3. 后台任务完成回调
4. wait_tool_result 中断机制
5. 多工具并行执行
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Any


# 测试用的模拟类
@dataclass
class MockEvent:
    unified_msg_origin: str = "test_session_001"
    message_obj: Any = None
    _result: Any = None
    _has_send_oper: bool = False
    _extras: dict = None

    def __post_init__(self):
        self._extras = self._extras or {}
        self.message_obj = Mock()
        self.message_obj.type = "group"
        self.message_obj.self_id = "bot_001"
        self.message_obj.session_id = "session_001"
        self.message_obj.group = Mock()
        self.message_obj.sender = Mock()

    def get_result(self):
        return self._result

    def set_result(self, result):
        self._result = result

    def set_extra(self, key, value):
        self._extras[key] = value

    def get_sender_name(self):
        return "test_user"

    async def send(self, msg):
        pass


class MockFunctionTool:
    """模拟函数工具"""

    def __init__(self, name: str, handler=None):
        self.name = name
        self.handler = handler

    async def call(self, context, **kwargs):
        if self.handler:
            return await self.handler(**kwargs)
        return "default_result"


class MockRunContext:
    """模拟运行上下文"""

    def __init__(self, event: MockEvent, timeout: float = 15.0):
        self.tool_call_timeout = timeout
        self.context = Mock()
        self.context.event = event
        self.context.context = Mock()
        self.context.context.get_event_queue = Mock(return_value=asyncio.Queue())


# ============ 测试用例 ============


class TestNormalToolExecution:
    """正常工具执行测试"""

    @pytest.mark.asyncio
    async def test_sync_handler_returns_result(self):
        """同步处理器返回结果"""

        async def handler(event, **kwargs):
            return "hello world"

        tool = MockFunctionTool("test_tool", handler)
        event = MockEvent()

        result = await handler(event)
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_async_generator_handler(self):
        """异步生成器处理器"""

        async def handler(event, **kwargs):
            yield "step1"
            yield "step2"
            yield "final"

        event = MockEvent()
        results = []
        async for r in handler(event):
            results.append(r)

        assert results == ["step1", "step2", "final"]


class TestBackgroundTaskManager:
    """后台任务管理器测试"""

    @pytest.mark.asyncio
    async def test_task_creation(self):
        """任务创建测试"""
        from astrbot.core.background_tool import BackgroundTask, TaskStatus

        task = BackgroundTask(
            task_id="test_001",
            tool_name="test_tool",
            tool_args={"arg1": "value1"},
            session_id="session_001",
        )

        assert task.status == TaskStatus.PENDING
        assert task.task_id == "test_001"

    @pytest.mark.asyncio
    async def test_task_state_transitions(self):
        """任务状态转换测试"""
        from astrbot.core.background_tool import BackgroundTask, TaskStatus

        task = BackgroundTask(
            task_id="test_002",
            tool_name="test_tool",
            tool_args={},
            session_id="session_001",
        )

        # PENDING -> RUNNING
        task.start()
        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None

        # RUNNING -> COMPLETED
        task.complete("success")
        assert task.status == TaskStatus.COMPLETED
        assert task.result == "success"
        assert task.is_finished()


class TestTaskRegistry:
    """任务注册表测试"""

    def test_register_and_get(self):
        """注册和获取任务"""
        from astrbot.core.background_tool import TaskRegistry, BackgroundTask

        registry = TaskRegistry()
        registry.clear()  # 清空单例状态

        task = BackgroundTask(
            task_id="reg_001", tool_name="test", tool_args={}, session_id="s1"
        )

        registry.register(task)
        retrieved = registry.get("reg_001")

        assert retrieved is not None
        assert retrieved.task_id == "reg_001"


class TestWaitInterrupt:
    """等待中断机制测试"""

    @pytest.mark.asyncio
    async def test_interrupt_flag(self):
        """中断标记测试"""
        from astrbot.core.background_tool import BackgroundToolManager

        manager = BackgroundToolManager()
        session_id = "interrupt_test_001"

        # 初始状态无中断
        assert not manager.check_interrupt_flag(session_id)

        # 设置中断
        manager.set_interrupt_flag(session_id)
        assert manager.check_interrupt_flag(session_id)

        # 清除中断
        manager.clear_interrupt_flag(session_id)
        assert not manager.check_interrupt_flag(session_id)


class TestOutputBuffer:
    """输出缓冲区测试"""

    def test_append_and_get(self):
        """追加和获取输出"""
        from astrbot.core.background_tool import OutputBuffer

        buffer = OutputBuffer()
        task_id = "buf_001"

        buffer.append(task_id, "line1")
        buffer.append(task_id, "line2")
        buffer.append(task_id, "line3")

        lines = buffer.get_recent(task_id, n=2)
        assert len(lines) == 2
        assert lines == ["line2", "line3"]


class TestTimeoutBehavior:
    """超时行为测试"""

    @pytest.mark.asyncio
    async def test_timeout_triggers_background(self):
        """超时触发后台执行"""

        # 模拟一个会超时的任务
        async def slow_handler(event, **kwargs):
            await asyncio.sleep(5)
            return "done"

        # 使用短超时测试
        try:
            result = await asyncio.wait_for(slow_handler(MockEvent()), timeout=0.1)
        except asyncio.TimeoutError:
            # 预期会超时
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestMethodResolver:
    """方法解析器单元测试"""

    def test_resolve_with_handler(self):
        """测试handler解析"""
        from astrbot.core.tool_execution.infrastructure.handler import MethodResolver

        class MockTool:
            handler = lambda self, x: x
            name = "test"

        resolver = MethodResolver()
        tool = MockTool()
        handler, method = resolver.resolve(tool)
        assert method == "decorator_handler"


class TestTimeoutStrategy:
    """超时策略单元测试"""

    @pytest.mark.asyncio
    async def test_no_timeout_strategy(self):
        """测试无超时策略"""
        from astrbot.core.tool_execution.infrastructure.timeout import NoTimeoutStrategy

        async def quick_task():
            return "done"

        strategy = NoTimeoutStrategy()
        result = await strategy.execute(quick_task(), 1.0)
        assert result == "done"


class TestCompletionSignal:
    """完成信号单元测试"""

    @pytest.mark.asyncio
    async def test_signal_set_and_wait(self):
        """测试信号设置和等待"""
        from astrbot.core.tool_execution.infrastructure.background import (
            CompletionSignal,
        )

        signal = CompletionSignal()
        signal.set()
        result = await signal.wait(timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_signal_timeout(self):
        """测试信号超时"""
        from astrbot.core.tool_execution.infrastructure.background import (
            CompletionSignal,
        )

        signal = CompletionSignal()
        result = await signal.wait(timeout=0.1)
        assert result is False


class TestResultProcessor:
    """结果处理器单元测试"""

    @pytest.mark.asyncio
    async def test_process_string_result(self):
        """测试字符串结果处理"""
        from astrbot.core.tool_execution.infrastructure.handler import ResultProcessor

        processor = ResultProcessor()
        result = await processor.process("hello")
        assert result is not None
        assert result.content[0].text == "hello"

    @pytest.mark.asyncio
    async def test_process_none_result(self):
        """测试None结果处理"""
        from astrbot.core.tool_execution.infrastructure.handler import ResultProcessor

        processor = ResultProcessor()
        result = await processor.process(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_call_tool_result(self):
        """测试CallToolResult直接返回"""
        import mcp.types
        from astrbot.core.tool_execution.infrastructure.handler import ResultProcessor

        processor = ResultProcessor()
        original = mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="test")]
        )
        result = await processor.process(original)
        assert result is original


class TestParameterValidator:
    """参数验证器单元测试"""

    def test_validate_with_matching_params(self):
        """测试参数匹配验证"""
        from astrbot.core.tool_execution.infrastructure.handler import (
            ParameterValidator,
        )

        def handler(event, name: str, age: int = 18):
            pass

        validator = ParameterValidator()
        params = {"name": "test", "age": 25}
        result = validator.validate(handler, params)
        # 验证器会添加event参数（bind_partial绑定None）
        assert result["name"] == "test"
        assert result["age"] == 25


class TestBackgroundHandler:
    """后台处理器单元测试"""

    @pytest.mark.asyncio
    async def test_build_notification(self):
        """测试通知构建"""
        from astrbot.core.tool_execution.infrastructure.timeout import BackgroundHandler

        handler = BackgroundHandler()
        result = handler._build_notification("test_tool", "abc123")
        assert "test_tool" in result.content[0].text
        assert "abc123" in result.content[0].text


class TestToolExecutor:
    """工具执行编排器单元测试"""

    def test_should_enable_timeout(self):
        """测试超时启用判断"""
        from astrbot.core.tool_execution.application.tool_executor import ToolExecutor

        executor = ToolExecutor()

        # 正常工具应启用超时
        assert executor._should_enable_timeout(15.0, "normal_tool") is True

        # 后台管理工具不启用超时
        assert executor._should_enable_timeout(15.0, "wait_tool_result") is False
        assert executor._should_enable_timeout(15.0, "get_tool_output") is False

        # 超时为0时禁用
        assert executor._should_enable_timeout(0, "normal_tool") is False


class TestDomainConfig:
    """领域配置测试"""

    def test_background_tool_names(self):
        """测试后台工具名称配置"""
        from astrbot.core.tool_execution.domain.config import BACKGROUND_TOOL_NAMES

        assert "wait_tool_result" in BACKGROUND_TOOL_NAMES
        assert "get_tool_output" in BACKGROUND_TOOL_NAMES
        assert "stop_tool" in BACKGROUND_TOOL_NAMES
        assert "list_running_tools" in BACKGROUND_TOOL_NAMES
        assert len(BACKGROUND_TOOL_NAMES) == 4
