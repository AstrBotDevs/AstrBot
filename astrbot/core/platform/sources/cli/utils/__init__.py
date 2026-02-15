"""CLI工具模块 - AOP装饰器集合

提供横切关注点的装饰器：
- 异常处理: handle_exceptions, CLIError, AuthenticationError, ValidationError, TimeoutError
- 重试机制: retry
- 超时控制: timeout
- 日志记录: log_entry_exit, log_performance, log_request
- 权限校验: require_auth, require_whitelist
- 组合装饰器: with_logging_and_error_handling
"""

from .decorators import (
    AuthenticationError,
    # 异常类
    CLIError,
    TimeoutError,
    ValidationError,
    # 异常处理
    handle_exceptions,
    # 日志
    log_entry_exit,
    log_performance,
    log_request,
    # 权限
    require_auth,
    require_whitelist,
    # 重试
    retry,
    # 超时
    timeout,
    # 组合
    with_logging_and_error_handling,
)

__all__ = [
    # 异常类
    "CLIError",
    "AuthenticationError",
    "ValidationError",
    "TimeoutError",
    # 异常处理
    "handle_exceptions",
    # 重试
    "retry",
    # 超时
    "timeout",
    # 日志
    "log_entry_exit",
    "log_performance",
    "log_request",
    # 权限
    "require_auth",
    "require_whitelist",
    # 组合
    "with_logging_and_error_handling",
]
