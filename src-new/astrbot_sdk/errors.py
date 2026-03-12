"""跨运行时边界传递的统一错误模型。"""

from __future__ import annotations

from dataclasses import dataclass


class ErrorCodes:
    """AstrBot v4 的稳定错误码常量。"""

    UNKNOWN_ERROR = "unknown_error"

    # retryable = False
    LLM_NOT_CONFIGURED = "llm_not_configured"
    CAPABILITY_NOT_FOUND = "capability_not_found"
    PERMISSION_DENIED = "permission_denied"
    LLM_ERROR = "llm_error"
    INVALID_INPUT = "invalid_input"
    CANCELLED = "cancelled"
    PROTOCOL_VERSION_MISMATCH = "protocol_version_mismatch"
    PROTOCOL_ERROR = "protocol_error"
    INTERNAL_ERROR = "internal_error"

    # retryable = True
    CAPABILITY_TIMEOUT = "capability_timeout"
    NETWORK_ERROR = "network_error"
    LLM_TEMPORARY_ERROR = "llm_temporary_error"


@dataclass(slots=True)
class AstrBotError(Exception):
    code: str
    message: str
    hint: str = ""
    retryable: bool = False

    def __str__(self) -> str:
        return self.message

    @classmethod
    def cancelled(cls, message: str = "调用被取消") -> "AstrBotError":
        return cls(
            code=ErrorCodes.CANCELLED,
            message=message,
            hint="",
            retryable=False,
        )

    @classmethod
    def capability_not_found(cls, name: str) -> "AstrBotError":
        return cls(
            code=ErrorCodes.CAPABILITY_NOT_FOUND,
            message=f"未找到能力：{name}",
            hint="请确认 AstrBot Core 是否已注册该 capability",
            retryable=False,
        )

    @classmethod
    def invalid_input(cls, message: str) -> "AstrBotError":
        return cls(
            code=ErrorCodes.INVALID_INPUT,
            message=message,
            hint="请检查调用参数",
            retryable=False,
        )

    @classmethod
    def protocol_version_mismatch(cls, message: str) -> "AstrBotError":
        return cls(
            code=ErrorCodes.PROTOCOL_VERSION_MISMATCH,
            message=message,
            hint="请升级 astrbot_sdk 至最新版本",
            retryable=False,
        )

    @classmethod
    def protocol_error(cls, message: str) -> "AstrBotError":
        return cls(
            code=ErrorCodes.PROTOCOL_ERROR,
            message=message,
            hint="请检查通信双方的协议实现",
            retryable=False,
        )

    @classmethod
    def internal_error(cls, message: str) -> "AstrBotError":
        return cls(
            code=ErrorCodes.INTERNAL_ERROR,
            message=message,
            hint="请联系插件作者",
            retryable=False,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "retryable": self.retryable,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "AstrBotError":
        return cls(
            code=str(payload.get("code", ErrorCodes.UNKNOWN_ERROR)),
            message=str(payload.get("message", "未知错误")),
            hint=str(payload.get("hint", "")),
            retryable=bool(payload.get("retryable", False)),
        )
