# =============================================================================
# 新旧对比 - errors.py
# =============================================================================
#
# 【旧版】
# 旧版 SDK 没有专门的 errors.py 文件。
# 只有 runtime/rpc/jsonrpc.py 中定义了 JSONRPCErrorData 用于内部通信。
#
# 【新版】
# 新增 errors.py，定义统一的 AstrBotError 异常类：
# - 包含 code, message, hint, retryable 字段
# - 提供工厂方法: cancelled(), capability_not_found(), invalid_input(),
#                protocol_version_mismatch(), protocol_error(), internal_error()
# - 支持序列化/反序列化: to_payload(), from_payload()
#
# 【设计目的】
# 新版采用分布式架构，插件与核心通过 RPC 通信。
# AstrBotError 提供统一的错误表示，便于跨进程传递错误信息。
#
# =============================================================================
# TODO: 功能缺失
# =============================================================================
#
# 1. 缺少旧版异常类兼容
#    - 如果旧版有其他异常类（如 ChatProviderNotFoundError），需要考虑兼容
#    - 当前 AstrBotError 可覆盖大部分场景
#
# 2. 缺少错误码常量定义
#    - 建议添加错误码枚举或常量，便于错误匹配
#    - 例如: ERROR_CODE_CANCELLED = "cancelled"
#
# =============================================================================

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
