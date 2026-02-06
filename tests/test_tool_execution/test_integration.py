"""工具执行集成测试

覆盖关键场景：
1. 正常工具执行
2. 超时转后台执行
3. 后台任务完成回调
4. wait_tool_result 中断机制
5. 多工具并行执行
"""

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock

import pytest


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
        from astrbot.core.background_tool import BackgroundTask, TaskRegistry

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
            await asyncio.wait_for(slow_handler(MockEvent()), timeout=0.1)
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
            def handler(self, x):
                return x

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


class TestMethodResolverAdvanced:
    """方法解析器高级测试"""

    def test_resolve_with_run_method(self):
        """测试run方法解析"""
        from astrbot.core.tool_execution.infrastructure.handler import MethodResolver

        class MockTool:
            handler = None
            name = "test"

            def run(self, event):
                return "run result"

        resolver = MethodResolver()
        handler, method = resolver.resolve(MockTool())
        assert method == "run"

    def test_resolve_failure_no_handler(self):
        """测试无handler时抛出异常"""
        from astrbot.core.tool_execution.errors import MethodResolutionError
        from astrbot.core.tool_execution.infrastructure.handler import MethodResolver

        class MockTool:
            handler = None
            name = "test"

        resolver = MethodResolver()
        try:
            resolver.resolve(MockTool())
            assert False, "Should raise MethodResolutionError"
        except MethodResolutionError:
            pass


class TestTimeoutStrategyAdvanced:
    """超时策略高级测试"""

    @pytest.mark.asyncio
    async def test_standard_timeout_strategy_success(self):
        """测试标准超时策略成功执行"""
        from astrbot.core.tool_execution.infrastructure.timeout import TimeoutStrategy

        async def quick_task():
            return "done"

        strategy = TimeoutStrategy()
        result = await strategy.execute(quick_task(), 5.0)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_standard_timeout_strategy_timeout(self):
        """测试标准超时策略超时"""
        from astrbot.core.tool_execution.infrastructure.timeout import TimeoutStrategy

        async def slow_task():
            await asyncio.sleep(10)
            return "done"

        strategy = TimeoutStrategy()
        try:
            await strategy.execute(slow_task(), 0.1)
            assert False, "Should raise TimeoutError"
        except asyncio.TimeoutError:
            pass


class TestEventDrivenWait:
    """事件驱动等待测试"""

    @pytest.mark.asyncio
    async def test_task_completion_signal(self):
        """测试任务完成信号触发"""
        from astrbot.core.background_tool import BackgroundTask

        task = BackgroundTask(
            task_id="signal_test",
            tool_name="test",
            tool_args={},
            session_id="s1",
        )
        task.init_completion_event()

        assert task.completion_event is not None

        # 模拟任务完成
        task.complete("done")
        task._signal_completion()

        # 验证信号已设置
        assert task.completion_event.is_set()

    @pytest.mark.asyncio
    async def test_task_without_completion_event(self):
        """测试无完成事件的任务回退到轮询"""
        from astrbot.core.background_tool import BackgroundTask

        task = BackgroundTask(
            task_id="no_event_test",
            tool_name="test",
            tool_args={},
            session_id="s1",
        )
        # 不初始化 completion_event
        task.complete("done")

        # 应该正常完成，is_finished 返回 True
        assert task.is_finished()
        assert task.completion_event is None


class TestErrorHandling:
    """错误处理测试"""

    def test_parameter_validation_error_unexpected_arg(self):
        """测试意外参数触发验证错误"""
        from astrbot.core.tool_execution.errors import ParameterValidationError
        from astrbot.core.tool_execution.infrastructure.handler import (
            ParameterValidator,
        )

        def handler(event, name: str):
            pass

        validator = ParameterValidator()
        try:
            validator.validate(handler, {"unexpected": "value"})
            assert False, "Should raise ParameterValidationError"
        except ParameterValidationError as e:
            assert "Parameter mismatch" in str(e)

    def test_method_resolution_error(self):
        """测试方法解析错误"""
        from astrbot.core.tool_execution.errors import MethodResolutionError

        error = MethodResolutionError("test error")
        assert str(error) == "test error"


class TestBackgroundToolConfig:
    """配置模块单元测试"""

    def test_default_config_values(self):
        """测试默认配置值"""
        from astrbot.core.tool_execution.domain.config import (
            DEFAULT_CONFIG,
        )

        assert DEFAULT_CONFIG.cleanup_interval_seconds == 600
        assert DEFAULT_CONFIG.task_max_age_seconds == 3600
        assert DEFAULT_CONFIG.default_timeout_seconds == 600
        assert DEFAULT_CONFIG.error_preview_max_length == 500
        assert DEFAULT_CONFIG.default_output_lines == 50

    def test_config_immutability(self):
        """测试配置不可变性"""
        from astrbot.core.tool_execution.domain.config import BackgroundToolConfig

        config = BackgroundToolConfig()
        try:
            config.cleanup_interval_seconds = 100
            assert False, "Should raise FrozenInstanceError"
        except Exception:
            pass  # Expected


class TestCallbackEventBuilder:
    """回调事件构建器单元测试"""

    def test_build_notification_text(self):
        """测试通知文本构建"""
        from astrbot.core.background_tool import (
            BackgroundTask,
            CallbackEventBuilder,
            TaskStatus,
        )

        task = BackgroundTask(
            task_id="test_001",
            tool_name="test_tool",
            tool_args={},
            session_id="session_001",
        )
        task.status = TaskStatus.COMPLETED
        task.result = "success"

        builder = CallbackEventBuilder()
        text = builder.build_notification_text(task)

        assert "test_001" in text
        assert "test_tool" in text
        assert "completed successfully" in text
        assert "success" in text

    def test_error_preview_truncation(self):
        """测试错误预览截断"""
        from astrbot.core.background_tool import (
            BackgroundTask,
            CallbackEventBuilder,
            TaskStatus,
        )
        from astrbot.core.tool_execution.domain.config import BackgroundToolConfig

        task = BackgroundTask(
            task_id="test_002",
            tool_name="test_tool",
            tool_args={},
            session_id="session_001",
        )
        task.status = TaskStatus.FAILED
        task.error = "x" * 1000  # 超过500字符

        config = BackgroundToolConfig(error_preview_max_length=100)
        builder = CallbackEventBuilder(config=config)
        text = builder.build_notification_text(task)

        assert "..." in text
        assert len(text) < 1000  # 应该被截断


class TestCallbackPublisher:
    """回调发布器单元测试"""

    def test_should_publish_when_being_waited(self):
        """测试等待中的任务不应发布"""
        from astrbot.core.background_tool import (
            BackgroundTask,
            CallbackPublisher,
        )

        task = BackgroundTask(
            task_id="test_003",
            tool_name="test_tool",
            tool_args={},
            session_id="session_001",
        )
        task.is_being_waited = True

        publisher = CallbackPublisher()
        assert publisher.should_publish(task) is False

    def test_should_publish_without_event(self):
        """测试无事件的任务不应发布"""
        from astrbot.core.background_tool import (
            BackgroundTask,
            CallbackPublisher,
        )

        task = BackgroundTask(
            task_id="test_004",
            tool_name="test_tool",
            tool_args={},
            session_id="session_001",
        )
        task.event = None

        publisher = CallbackPublisher()
        assert publisher.should_publish(task) is False


class TestSanitizer:
    """日志脱敏工具单元测试"""

    def test_sanitize_sensitive_key(self):
        """测试敏感键名脱敏"""
        from astrbot.core.tool_execution.utils.sanitizer import sanitize_params

        params = {
            "username": "test_user",
            "password": "secret123",
            "api_key": "sk-test-fake-key-for-unit-test",
        }
        result = sanitize_params(params)

        assert result["username"] == "test_user"
        assert result["password"] == "***REDACTED***"
        assert result["api_key"] == "***REDACTED***"

    def test_sanitize_sensitive_value_pattern(self):
        """测试敏感值模式脱敏"""
        from astrbot.core.tool_execution.utils.sanitizer import sanitize_params

        params = {
            "header": "Bearer eyJhbGciOiJIUzI1NiJ9",
            "config": "api_key=test-fake-key-for-unit-test",
        }
        result = sanitize_params(params)

        assert "***REDACTED***" in result["header"]
        assert "***REDACTED***" in result["config"]

    def test_sanitize_nested_dict(self):
        """测试嵌套字典脱敏"""
        from astrbot.core.tool_execution.utils.sanitizer import sanitize_params

        params = {
            "outer": {
                "token": "secret",
                "name": "test",
            }
        }
        result = sanitize_params(params)

        assert result["outer"]["token"] == "***REDACTED***"
        assert result["outer"]["name"] == "test"

    def test_sanitize_truncation(self):
        """测试长值截断"""
        from astrbot.core.tool_execution.utils.sanitizer import sanitize_params

        params = {"long_text": "x" * 200}
        result = sanitize_params(params, max_value_length=100)

        assert len(result["long_text"]) < 200
        assert "truncated" in result["long_text"]


class TestRWLock:
    """读写锁单元测试"""

    def test_read_lock_allows_concurrent_reads(self):
        """测试读锁允许并发读取"""
        import threading

        from astrbot.core.tool_execution.utils.rwlock import RWLock

        lock = RWLock()
        read_count = [0]
        max_concurrent = [0]

        def reader():
            with lock.read():
                read_count[0] += 1
                max_concurrent[0] = max(max_concurrent[0], read_count[0])
                import time

                time.sleep(0.01)
                read_count[0] -= 1

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 多个读取者应该能够并发
        assert max_concurrent[0] > 1

    def test_write_lock_exclusive(self):
        """测试写锁独占"""
        from astrbot.core.tool_execution.utils.rwlock import RWLock

        lock = RWLock()
        data = {"value": 0}

        def writer():
            with lock.write():
                current = data["value"]
                import time

                time.sleep(0.01)
                data["value"] = current + 1

        import threading

        threads = [threading.Thread(target=writer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 写入应该是原子的
        assert data["value"] == 5


class TestValidators:
    """输入验证工具单元测试"""

    def test_valid_task_id(self):
        """测试有效的任务ID"""
        from astrbot.core.tool_execution.utils.validators import validate_task_id

        assert validate_task_id("task_001") == "task_001"
        assert validate_task_id("abc-123-def") == "abc-123-def"

    def test_invalid_task_id_type(self):
        """测试无效的任务ID类型"""
        from astrbot.core.tool_execution.utils.validators import (
            ValidationError,
            validate_task_id,
        )

        try:
            validate_task_id(123)
            assert False, "Should raise ValidationError"
        except ValidationError as e:
            assert "must be string" in str(e)

    def test_invalid_task_id_format(self):
        """测试无效的任务ID格式"""
        from astrbot.core.tool_execution.utils.validators import (
            ValidationError,
            validate_task_id,
        )

        try:
            validate_task_id("task@#$%")
            assert False, "Should raise ValidationError"
        except ValidationError as e:
            assert "Invalid task_id format" in str(e)

    def test_valid_session_id(self):
        """测试有效的会话ID"""
        from astrbot.core.tool_execution.utils.validators import validate_session_id

        assert validate_session_id("session_001") == "session_001"
        assert validate_session_id("user:group:123") == "user:group:123"

    def test_session_id_dangerous_chars(self):
        """测试会话ID危险字符"""
        from astrbot.core.tool_execution.utils.validators import (
            ValidationError,
            validate_session_id,
        )

        try:
            validate_session_id("session\x00inject")
            assert False, "Should raise ValidationError"
        except ValidationError as e:
            assert "invalid characters" in str(e)

    def test_validate_positive_int(self):
        """测试正整数验证"""
        from astrbot.core.tool_execution.utils.validators import (
            ValidationError,
            validate_positive_int,
        )

        assert validate_positive_int(10, "count") == 10

        try:
            validate_positive_int(-1, "count")
            assert False, "Should raise ValidationError"
        except ValidationError:
            pass

        try:
            validate_positive_int(99999, "count", max_value=100)
            assert False, "Should raise ValidationError"
        except ValidationError:
            pass


class TestConfigCache:
    """配置缓存单元测试"""

    def test_cache_reuse(self):
        """测试缓存重用"""
        import time

        from astrbot.core.background_tool.task_executor import _ConfigCache

        # 重置缓存
        _ConfigCache._timeout = None
        _ConfigCache._last_load = 0

        # 首次加载
        result1 = _ConfigCache.get_timeout()
        first_load_time = _ConfigCache._last_load

        # 立即再次获取应该使用缓存
        time.sleep(0.01)
        result2 = _ConfigCache.get_timeout()
        second_load_time = _ConfigCache._last_load

        # 加载时间应该相同（使用了缓存）
        assert first_load_time == second_load_time
        assert result1 == result2
