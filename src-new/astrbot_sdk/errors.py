from __future__ import annotations

from dataclasses import dataclass


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
            code="cancelled",
            message=message,
            hint="",
            retryable=False,
        )

    @classmethod
    def capability_not_found(cls, name: str) -> "AstrBotError":
        return cls(
            code="capability_not_found",
            message=f"未找到能力：{name}",
            hint="请确认 AstrBot Core 是否已注册该 capability",
            retryable=False,
        )

    @classmethod
    def invalid_input(cls, message: str) -> "AstrBotError":
        return cls(
            code="invalid_input",
            message=message,
            hint="请检查调用参数",
            retryable=False,
        )

    @classmethod
    def protocol_version_mismatch(cls, message: str) -> "AstrBotError":
        return cls(
            code="protocol_version_mismatch",
            message=message,
            hint="请升级 astrbot_sdk 至最新版本",
            retryable=False,
        )

    @classmethod
    def protocol_error(cls, message: str) -> "AstrBotError":
        return cls(
            code="protocol_error",
            message=message,
            hint="请检查通信双方的协议实现",
            retryable=False,
        )

    @classmethod
    def internal_error(cls, message: str) -> "AstrBotError":
        return cls(
            code="internal_error",
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
            code=str(payload.get("code", "unknown_error")),
            message=str(payload.get("message", "未知错误")),
            hint=str(payload.get("hint", "")),
            retryable=bool(payload.get("retryable", False)),
        )
