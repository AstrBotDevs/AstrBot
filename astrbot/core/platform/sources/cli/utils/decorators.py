"""AOP装饰器集合

将横切关注点（日志、异常处理、权限校验、重试）从业务代码中抽离。
遵循单一职责原则，每个装饰器只处理一个关注点。
"""

import asyncio
import functools
import time
from collections.abc import Callable
from typing import TypeVar

from astrbot import logger

F = TypeVar("F", bound=Callable)


# ============================================================
# 异常处理装饰器
# ============================================================


class CLIError(Exception):
    """CLI模块基础异常"""

    def __init__(self, message: str, error_code: str = "CLI_ERROR"):
        super().__init__(message)
        self.error_code = error_code


class AuthenticationError(CLIError):
    """认证失败异常"""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTH_FAILED")


class ValidationError(CLIError):
    """验证失败异常"""

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, "VALIDATION_ERROR")


class TimeoutError(CLIError):
    """超时异常"""

    def __init__(self, message: str = "Operation timed out"):
        super().__init__(message, "TIMEOUT")


def handle_exceptions(
    *exception_types: type[Exception],
    default_return=None,
    reraise: bool = False,
    log_level: str = "error",
):
    """统一异常处理装饰器

    Args:
        exception_types: 要捕获的异常类型，默认捕获所有Exception
        default_return: 异常时的默认返回值
        reraise: 是否重新抛出异常
        log_level: 日志级别 (debug/info/warning/error)
    """
    if not exception_types:
        exception_types = (Exception,)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except exception_types as e:
                _log_exception(func.__qualname__, e, log_level)
                if reraise:
                    raise
                return default_return

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exception_types as e:
                _log_exception(func.__qualname__, e, log_level)
                if reraise:
                    raise
                return default_return

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _log_exception(func_name: str, exc: Exception, level: str) -> None:
    """记录异常日志"""
    log_func = getattr(logger, level, logger.error)
    error_code = getattr(exc, "error_code", "UNKNOWN")
    log_func("[EXCEPTION] %s: %s (code=%s)", func_name, exc, error_code)


# ============================================================
# 重试装饰器
# ============================================================


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """重试装饰器

    Args:
        max_attempts: 最大重试次数
        delay: 初始延迟（秒）
        backoff: 延迟倍增因子
        exceptions: 触发重试的异常类型
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            "[RETRY] %s attempt %d/%d failed: %s, retrying in %.1fs",
                            func.__qualname__,
                            attempt + 1,
                            max_attempts,
                            e,
                            current_delay,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            "[RETRY] %s all %d attempts failed",
                            func.__qualname__,
                            max_attempts,
                        )

            raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            "[RETRY] %s attempt %d/%d failed: %s, retrying in %.1fs",
                            func.__qualname__,
                            attempt + 1,
                            max_attempts,
                            e,
                            current_delay,
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            "[RETRY] %s all %d attempts failed",
                            func.__qualname__,
                            max_attempts,
                        )

            raise last_exception

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============================================================
# 超时装饰器
# ============================================================


def timeout(seconds: float):
    """超时装饰器

    Args:
        seconds: 超时时间（秒）
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=seconds,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "[TIMEOUT] %s exceeded %.1fs",
                    func.__qualname__,
                    seconds,
                )
                raise TimeoutError(f"{func.__qualname__} timed out after {seconds}s")

        if not asyncio.iscoroutinefunction(func):
            raise TypeError("timeout decorator only supports async functions")

        return async_wrapper

    return decorator


# ============================================================
# 日志装饰器
# ============================================================


def log_entry_exit(func: F) -> F:
    """记录函数入口和出口的装饰器

    用于异步函数，记录调用开始和结束。
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        func_name = func.__qualname__
        logger.debug("[ENTRY] %s", func_name)
        try:
            result = await func(*args, **kwargs)
            logger.debug("[EXIT] %s", func_name)
            return result
        except Exception as e:
            logger.error("[ERROR] %s: %s", func_name, e)
            raise

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        func_name = func.__qualname__
        logger.debug("[ENTRY] %s", func_name)
        try:
            result = func(*args, **kwargs)
            logger.debug("[EXIT] %s", func_name)
            return result
        except Exception as e:
            logger.error("[ERROR] %s: %s", func_name, e)
            raise

    import asyncio

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


def log_performance(threshold_ms: float = 100.0):
    """记录性能的装饰器

    当执行时间超过阈值时记录警告。

    Args:
        threshold_ms: 阈值（毫秒）
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                if elapsed_ms > threshold_ms:
                    logger.warning(
                        "[PERF] %s took %.2fms (threshold: %.2fms)",
                        func.__qualname__,
                        elapsed_ms,
                        threshold_ms,
                    )

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                if elapsed_ms > threshold_ms:
                    logger.warning(
                        "[PERF] %s took %.2fms (threshold: %.2fms)",
                        func.__qualname__,
                        elapsed_ms,
                        threshold_ms,
                    )

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def log_request(func: F) -> F:
    """记录请求处理的装饰器

    专门用于请求处理函数，记录请求ID和处理结果。
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        request_id = kwargs.get("request_id", "unknown")
        func_name = func.__qualname__

        logger.info("[REQUEST] %s started, request_id=%s", func_name, request_id)
        start = time.perf_counter()

        try:
            result = await func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "[REQUEST] %s completed, request_id=%s, elapsed=%.2fms",
                func_name,
                request_id,
                elapsed_ms,
            )
            return result
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "[REQUEST] %s failed, request_id=%s, elapsed=%.2fms, error=%s",
                func_name,
                request_id,
                elapsed_ms,
                e,
            )
            raise

    return wrapper


# ============================================================
# 权限校验装饰器
# ============================================================


def require_auth(token_getter: Callable[[], str | None] = None):
    """权限校验装饰器

    Args:
        token_getter: 获取有效token的函数，返回None表示禁用验证
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 从kwargs获取提供的token
            provided_token = kwargs.get("auth_token", "")

            # 获取有效token
            valid_token = token_getter() if token_getter else None

            # 如果没有配置token，跳过验证
            if valid_token is None:
                return await func(*args, **kwargs)

            # 验证token
            if not provided_token:
                logger.warning("[AUTH] Missing auth_token")
                raise AuthenticationError("Missing authentication token")

            if provided_token != valid_token:
                logger.warning(
                    "[AUTH] Invalid auth_token (length=%d)", len(provided_token)
                )
                raise AuthenticationError("Invalid authentication token")

            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            provided_token = kwargs.get("auth_token", "")
            valid_token = token_getter() if token_getter else None

            if valid_token is None:
                return func(*args, **kwargs)

            if not provided_token:
                logger.warning("[AUTH] Missing auth_token")
                raise AuthenticationError("Missing authentication token")

            if provided_token != valid_token:
                logger.warning(
                    "[AUTH] Invalid auth_token (length=%d)", len(provided_token)
                )
                raise AuthenticationError("Invalid authentication token")

            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def require_whitelist(
    whitelist: list[str] = None, id_getter: Callable[[tuple, dict], str] = None
):
    """白名单校验装饰器

    Args:
        whitelist: 允许的ID列表，空列表表示允许所有
        id_getter: 从参数中获取ID的函数
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if whitelist and id_getter:
                request_id = id_getter(args, kwargs)
                if request_id not in whitelist:
                    logger.warning("[WHITELIST] Rejected request from: %s", request_id)
                    raise AuthenticationError(f"ID {request_id} not in whitelist")
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if whitelist and id_getter:
                request_id = id_getter(args, kwargs)
                if request_id not in whitelist:
                    logger.warning("[WHITELIST] Rejected request from: %s", request_id)
                    raise AuthenticationError(f"ID {request_id} not in whitelist")
            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============================================================
# 组合装饰器
# ============================================================


def with_logging_and_error_handling(
    log_entry: bool = True,
    log_perf: bool = False,
    perf_threshold_ms: float = 100.0,
    handle_errors: bool = True,
    default_return=None,
):
    """组合装饰器：日志 + 异常处理

    简化常见的装饰器组合使用。

    Args:
        log_entry: 是否记录入口/出口
        log_perf: 是否记录性能
        perf_threshold_ms: 性能阈值
        handle_errors: 是否处理异常
        default_return: 异常时的默认返回值
    """

    def decorator(func: F) -> F:
        decorated = func

        if handle_errors:
            decorated = handle_exceptions(default_return=default_return)(decorated)

        if log_perf:
            decorated = log_performance(perf_threshold_ms)(decorated)

        if log_entry:
            decorated = log_entry_exit(decorated)

        return decorated

    return decorator
