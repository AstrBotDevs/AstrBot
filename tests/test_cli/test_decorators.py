"""AOP装饰器单元测试"""

import asyncio

import pytest


class TestExceptionClasses:
    """异常类测试"""

    def test_cli_error(self):
        """测试CLI基础异常"""
        from astrbot.core.platform.sources.cli.utils.decorators import CLIError

        error = CLIError("Test error", "TEST_CODE")
        assert str(error) == "Test error"
        assert error.error_code == "TEST_CODE"

    def test_authentication_error(self):
        """测试认证异常"""
        from astrbot.core.platform.sources.cli.utils.decorators import (
            AuthenticationError,
        )

        error = AuthenticationError()
        assert error.error_code == "AUTH_FAILED"

        error2 = AuthenticationError("Custom message")
        assert str(error2) == "Custom message"

    def test_validation_error(self):
        """测试验证异常"""
        from astrbot.core.platform.sources.cli.utils.decorators import ValidationError

        error = ValidationError()
        assert error.error_code == "VALIDATION_ERROR"

    def test_timeout_error(self):
        """测试超时异常"""
        from astrbot.core.platform.sources.cli.utils.decorators import TimeoutError

        error = TimeoutError()
        assert error.error_code == "TIMEOUT"


class TestHandleExceptions:
    """异常处理装饰器测试"""

    def test_sync_no_exception(self):
        """测试同步函数无异常"""
        from astrbot.core.platform.sources.cli.utils.decorators import handle_exceptions

        @handle_exceptions()
        def func():
            return "success"

        assert func() == "success"

    def test_sync_with_exception(self):
        """测试同步函数有异常"""
        from astrbot.core.platform.sources.cli.utils.decorators import handle_exceptions

        @handle_exceptions(default_return="default")
        def func():
            raise ValueError("test error")

        assert func() == "default"

    def test_sync_reraise(self):
        """测试同步函数重新抛出异常"""
        from astrbot.core.platform.sources.cli.utils.decorators import handle_exceptions

        @handle_exceptions(reraise=True)
        def func():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            func()

    @pytest.mark.asyncio
    async def test_async_no_exception(self):
        """测试异步函数无异常"""
        from astrbot.core.platform.sources.cli.utils.decorators import handle_exceptions

        @handle_exceptions()
        async def func():
            return "success"

        assert await func() == "success"

    @pytest.mark.asyncio
    async def test_async_with_exception(self):
        """测试异步函数有异常"""
        from astrbot.core.platform.sources.cli.utils.decorators import handle_exceptions

        @handle_exceptions(default_return="default")
        async def func():
            raise ValueError("test error")

        assert await func() == "default"


class TestRetry:
    """重试装饰器测试"""

    def test_sync_success_first_try(self):
        """测试同步函数首次成功"""
        from astrbot.core.platform.sources.cli.utils.decorators import retry

        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def func():
            nonlocal call_count
            call_count += 1
            return "success"

        assert func() == "success"
        assert call_count == 1

    def test_sync_success_after_retry(self):
        """测试同步函数重试后成功"""
        from astrbot.core.platform.sources.cli.utils.decorators import retry

        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("retry")
            return "success"

        assert func() == "success"
        assert call_count == 3

    def test_sync_all_attempts_fail(self):
        """测试同步函数所有重试失败"""
        from astrbot.core.platform.sources.cli.utils.decorators import retry

        @retry(max_attempts=3, delay=0.01)
        def func():
            raise ValueError("always fail")

        with pytest.raises(ValueError):
            func()

    @pytest.mark.asyncio
    async def test_async_success_after_retry(self):
        """测试异步函数重试后成功"""
        from astrbot.core.platform.sources.cli.utils.decorators import retry

        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        async def func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "success"

        assert await func() == "success"
        assert call_count == 2


class TestTimeout:
    """超时装饰器测试"""

    @pytest.mark.asyncio
    async def test_no_timeout(self):
        """测试无超时"""
        from astrbot.core.platform.sources.cli.utils.decorators import timeout

        @timeout(1.0)
        async def func():
            return "success"

        assert await func() == "success"

    @pytest.mark.asyncio
    async def test_timeout_exceeded(self):
        """测试超时"""
        from astrbot.core.platform.sources.cli.utils.decorators import (
            TimeoutError,
            timeout,
        )

        @timeout(0.01)
        async def func():
            await asyncio.sleep(1.0)
            return "success"

        with pytest.raises(TimeoutError):
            await func()

    def test_sync_not_supported(self):
        """测试同步函数不支持"""
        from astrbot.core.platform.sources.cli.utils.decorators import timeout

        with pytest.raises(TypeError):

            @timeout(1.0)
            def func():
                return "success"


class TestLogEntryExit:
    """日志入口出口装饰器测试"""

    def test_sync_function(self):
        """测试同步函数"""
        from astrbot.core.platform.sources.cli.utils.decorators import log_entry_exit

        @log_entry_exit
        def func():
            return "success"

        assert func() == "success"

    @pytest.mark.asyncio
    async def test_async_function(self):
        """测试异步函数"""
        from astrbot.core.platform.sources.cli.utils.decorators import log_entry_exit

        @log_entry_exit
        async def func():
            return "success"

        assert await func() == "success"

    def test_sync_with_exception(self):
        """测试同步函数异常"""
        from astrbot.core.platform.sources.cli.utils.decorators import log_entry_exit

        @log_entry_exit
        def func():
            raise ValueError("test")

        with pytest.raises(ValueError):
            func()


class TestLogPerformance:
    """性能日志装饰器测试"""

    def test_sync_under_threshold(self):
        """测试同步函数低于阈值"""
        from astrbot.core.platform.sources.cli.utils.decorators import log_performance

        @log_performance(threshold_ms=1000.0)
        def func():
            return "success"

        assert func() == "success"

    @pytest.mark.asyncio
    async def test_async_under_threshold(self):
        """测试异步函数低于阈值"""
        from astrbot.core.platform.sources.cli.utils.decorators import log_performance

        @log_performance(threshold_ms=1000.0)
        async def func():
            return "success"

        assert await func() == "success"


class TestRequireAuth:
    """权限校验装饰器测试"""

    def test_sync_valid_token(self):
        """测试同步函数有效token"""
        from astrbot.core.platform.sources.cli.utils.decorators import require_auth

        @require_auth(token_getter=lambda: "valid_token")
        def func(auth_token=None):
            return "success"

        assert func(auth_token="valid_token") == "success"

    def test_sync_invalid_token(self):
        """测试同步函数无效token"""
        from astrbot.core.platform.sources.cli.utils.decorators import (
            AuthenticationError,
            require_auth,
        )

        @require_auth(token_getter=lambda: "valid_token")
        def func(auth_token=None):
            return "success"

        with pytest.raises(AuthenticationError):
            func(auth_token="wrong_token")

    def test_sync_missing_token(self):
        """测试同步函数缺少token"""
        from astrbot.core.platform.sources.cli.utils.decorators import (
            AuthenticationError,
            require_auth,
        )

        @require_auth(token_getter=lambda: "valid_token")
        def func(auth_token=None):
            return "success"

        with pytest.raises(AuthenticationError):
            func()

    def test_sync_disabled_auth(self):
        """测试同步函数禁用验证"""
        from astrbot.core.platform.sources.cli.utils.decorators import require_auth

        @require_auth(token_getter=lambda: None)
        def func(auth_token=None):
            return "success"

        # 禁用验证时任何token都通过
        assert func(auth_token="any") == "success"
        assert func() == "success"

    @pytest.mark.asyncio
    async def test_async_valid_token(self):
        """测试异步函数有效token"""
        from astrbot.core.platform.sources.cli.utils.decorators import require_auth

        @require_auth(token_getter=lambda: "valid_token")
        async def func(auth_token=None):
            return "success"

        assert await func(auth_token="valid_token") == "success"


class TestRequireWhitelist:
    """白名单校验装饰器测试"""

    def test_sync_in_whitelist(self):
        """测试同步函数在白名单中"""
        from astrbot.core.platform.sources.cli.utils.decorators import require_whitelist

        @require_whitelist(
            whitelist=["user1", "user2"],
            id_getter=lambda args, kwargs: kwargs.get("user_id"),
        )
        def func(user_id=None):
            return "success"

        assert func(user_id="user1") == "success"

    def test_sync_not_in_whitelist(self):
        """测试同步函数不在白名单中"""
        from astrbot.core.platform.sources.cli.utils.decorators import (
            AuthenticationError,
            require_whitelist,
        )

        @require_whitelist(
            whitelist=["user1", "user2"],
            id_getter=lambda args, kwargs: kwargs.get("user_id"),
        )
        def func(user_id=None):
            return "success"

        with pytest.raises(AuthenticationError):
            func(user_id="user3")

    def test_sync_empty_whitelist(self):
        """测试同步函数空白名单（允许所有）"""
        from astrbot.core.platform.sources.cli.utils.decorators import require_whitelist

        @require_whitelist(whitelist=[], id_getter=lambda args, kwargs: "any")
        def func():
            return "success"

        assert func() == "success"


class TestCombinedDecorator:
    """组合装饰器测试"""

    def test_with_logging_and_error_handling(self):
        """测试组合装饰器"""
        from astrbot.core.platform.sources.cli.utils.decorators import (
            with_logging_and_error_handling,
        )

        @with_logging_and_error_handling(
            log_entry=True,
            handle_errors=True,
            default_return="error",
        )
        def func():
            raise ValueError("test")

        assert func() == "error"

    def test_with_logging_no_error(self):
        """测试组合装饰器无错误"""
        from astrbot.core.platform.sources.cli.utils.decorators import (
            with_logging_and_error_handling,
        )

        @with_logging_and_error_handling(log_entry=True, handle_errors=False)
        def func():
            return "success"

        assert func() == "success"
