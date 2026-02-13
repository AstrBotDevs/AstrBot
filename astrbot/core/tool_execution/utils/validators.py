"""输入验证工具

验证用户输入的参数，防止注入攻击。
"""

import re
from typing import Any

# 有效的 task_id/session_id 模式（只允许字母、数字、下划线、连字符）
VALID_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")


class ValidationError(ValueError):
    """验证错误"""

    pass


def validate_task_id(task_id: Any) -> str:
    """验证任务ID

    Args:
        task_id: 任务ID

    Returns:
        验证后的任务ID

    Raises:
        ValidationError: 验证失败
    """
    if not isinstance(task_id, str):
        raise ValidationError(f"task_id must be string, got {type(task_id).__name__}")

    if not task_id:
        raise ValidationError("task_id cannot be empty")

    if not VALID_ID_PATTERN.match(task_id):
        raise ValidationError(
            "Invalid task_id format: must be 1-128 alphanumeric characters, "
            "underscores, or hyphens"
        )

    return task_id


def validate_session_id(session_id: Any) -> str:
    """验证会话ID

    Args:
        session_id: 会话ID

    Returns:
        验证后的会话ID

    Raises:
        ValidationError: 验证失败
    """
    if not isinstance(session_id, str):
        raise ValidationError(
            f"session_id must be string, got {type(session_id).__name__}"
        )

    if not session_id:
        raise ValidationError("session_id cannot be empty")

    # session_id 允许更宽松的格式（可能包含特殊字符如 : / 等）
    if len(session_id) > 256:
        raise ValidationError("session_id too long (max 256 characters)")

    # 检查是否包含危险字符
    dangerous_chars = ["\x00", "\n", "\r"]
    for char in dangerous_chars:
        if char in session_id:
            raise ValidationError("session_id contains invalid characters")

    return session_id


def validate_positive_int(value: Any, name: str, max_value: int = 10000) -> int:
    """验证正整数

    Args:
        value: 值
        name: 参数名称
        max_value: 最大允许值

    Returns:
        验证后的整数

    Raises:
        ValidationError: 验证失败
    """
    if not isinstance(value, int):
        raise ValidationError(f"{name} must be integer, got {type(value).__name__}")

    if value <= 0:
        raise ValidationError(f"{name} must be positive")

    if value > max_value:
        raise ValidationError(f"{name} too large (max {max_value})")

    return value
