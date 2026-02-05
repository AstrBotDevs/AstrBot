"""日志脱敏工具

防止敏感信息泄露到日志中。
"""

import re
from typing import Any


# 敏感参数名称（不区分大小写）
SENSITIVE_PARAM_NAMES = frozenset({
    "password",
    "passwd",
    "pwd",
    "token",
    "api_key",
    "apikey",
    "secret",
    "credential",
    "credentials",
    "auth",
    "authorization",
    "access_token",
    "refresh_token",
    "private_key",
    "privatekey",
    "secret_key",
    "secretkey",
    "key",  # 通用key
    "session_id",
    "cookie",
    "cookies",
})

# 用于替换的掩码
MASK = "***REDACTED***"

# 敏感值模式（用于检测值中的敏感内容）
SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[a-z0-9\-_.]+", re.IGNORECASE),  # Bearer token
    re.compile(r"(?i)(api[_-]?key[=:]\s*)[a-z0-9\-_.]+", re.IGNORECASE),  # API key in value
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI-style API key
    re.compile(r"ghp_[a-zA-Z0-9]{36,}"),  # GitHub token
    re.compile(r"gho_[a-zA-Z0-9]{36,}"),  # GitHub OAuth token
]


def _is_sensitive_key(key: str) -> bool:
    """检查键名是否为敏感参数"""
    key_lower = key.lower()
    return any(sensitive in key_lower for sensitive in SENSITIVE_PARAM_NAMES)


def _mask_sensitive_value(value: str) -> str:
    """对值中的敏感内容进行掩码处理"""
    result = value
    for pattern in SENSITIVE_VALUE_PATTERNS:
        result = pattern.sub(lambda m: m.group(1) + MASK if m.lastindex else MASK, result)
    return result


def sanitize_params(params: dict[str, Any], max_value_length: int = 100) -> dict[str, Any]:
    """脱敏参数字典

    Args:
        params: 原始参数字典
        max_value_length: 值的最大显示长度

    Returns:
        脱敏后的参数字典（副本）
    """
    if not params:
        return {}

    sanitized = {}
    for key, value in params.items():
        # 检查键名是否敏感
        if _is_sensitive_key(key):
            sanitized[key] = MASK
            continue

        # 处理值
        if isinstance(value, str):
            # 对字符串值进行模式检查
            masked = _mask_sensitive_value(value)
            # 截断过长的值
            if len(masked) > max_value_length:
                masked = masked[:max_value_length] + "...(truncated)"
            sanitized[key] = masked
        elif isinstance(value, dict):
            # 递归处理嵌套字典
            sanitized[key] = sanitize_params(value, max_value_length)
        elif isinstance(value, (list, tuple)):
            # 处理列表/元组
            sanitized[key] = [
                sanitize_params(v, max_value_length) if isinstance(v, dict)
                else _mask_sensitive_value(str(v)) if isinstance(v, str)
                else v
                for v in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def sanitize_for_log(params: dict[str, Any]) -> str:
    """将参数字典转为安全的日志字符串

    Args:
        params: 原始参数字典

    Returns:
        脱敏后的字符串表示
    """
    sanitized = sanitize_params(params)
    return str(sanitized)
