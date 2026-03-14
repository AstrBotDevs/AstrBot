"""跨运行时边界传递的统一错误模型。

AstrBotError 是 SDK 中所有可预期错误的标准格式，
支持跨进程传递（通过 to_payload/from_payload 序列化）。

错误处理流程：
    1. 运行时抛出 AstrBotError 子类或实例
    2. 错误被捕获并序列化为 payload
    3. 跨进程传输后反序列化
    4. 在 on_error 钩子中统一处理

Example:
    # 抛出错误
    raise AstrBotError.invalid_input("参数不能为空")

    # 捕获并处理
    try:
        await some_operation()
    except AstrBotError as e:
        if e.retryable:
            # 可重试的错误
            await retry()
        else:
            # 不可重试的错误
            await event.reply(e.hint or e.message)
"""

from __future__ import annotations

from dataclasses import dataclass


class ErrorCodes:
    """AstrBot v4 的稳定错误码常量。

    这些错误码在协议层稳定，不应随意更改。
    新增错误码应放在对应分类的末尾。

    分类：
        - 不可重试错误（retryable=False）：配置错误、权限错误等
        - 可重试错误（retryable=True）：网络超时、临时故障等
    """

    UNKNOWN_ERROR = "unknown_error"

    # 不可重试错误 - 配置或使用问题
    LLM_NOT_CONFIGURED = "llm_not_configured"
    CAPABILITY_NOT_FOUND = "capability_not_found"
    PERMISSION_DENIED = "permission_denied"
    LLM_ERROR = "llm_error"
    INVALID_INPUT = "invalid_input"
    CANCELLED = "cancelled"
    PROTOCOL_VERSION_MISMATCH = "protocol_version_mismatch"
    PROTOCOL_ERROR = "protocol_error"
    INTERNAL_ERROR = "internal_error"

    # 可重试错误 - 临时故障
    CAPABILITY_TIMEOUT = "capability_timeout"
    NETWORK_ERROR = "network_error"
    LLM_TEMPORARY_ERROR = "llm_temporary_error"


@dataclass(slots=True)
class AstrBotError(Exception):
    """AstrBot SDK 的标准错误类型。

    所有可预期的错误都应使用此类或其工厂方法创建。
    支持跨进程传递，包含用户友好的提示信息。

    Attributes:
        code: 错误码，来自 ErrorCodes 常量
        message: 错误消息，面向开发者
        hint: 用户提示，面向终端用户
        retryable: 是否可重试

    Example:
        # 使用工厂方法创建错误
        raise AstrBotError.invalid_input("参数格式错误", hint="请使用 JSON 格式")

        # 检查错误类型
        try:
            await operation()
        except AstrBotError as e:
            if e.code == ErrorCodes.CAPABILITY_NOT_FOUND:
                logger.error(f"能力不存在: {e.message}")
    """

    code: str
    message: str
    hint: str = ""
    retryable: bool = False

    def __str__(self) -> str:
        return self.message

    @classmethod
    def cancelled(cls, message: str = "调用被取消") -> "AstrBotError":
        """创建取消错误。

        Args:
            message: 错误消息

        Returns:
            AstrBotError 实例
        """
        return cls(
            code=ErrorCodes.CANCELLED,
            message=message,
            hint="",
            retryable=False,
        )

    @classmethod
    def capability_not_found(cls, name: str) -> "AstrBotError":
        """创建能力未找到错误。

        Args:
            name: 未找到的能力名称

        Returns:
            AstrBotError 实例
        """
        return cls(
            code=ErrorCodes.CAPABILITY_NOT_FOUND,
            message=f"未找到能力：{name}",
            hint="请确认 AstrBot Core 是否已注册该 capability",
            retryable=False,
        )

    @classmethod
    def invalid_input(
        cls,
        message: str,
        *,
        hint: str = "请检查调用参数",
    ) -> "AstrBotError":
        """创建输入无效错误。

        Args:
            message: 详细错误消息
            hint: 用户提示

        Returns:
            AstrBotError 实例
        """
        return cls(
            code=ErrorCodes.INVALID_INPUT,
            message=message,
            hint=hint,
            retryable=False,
        )

    @classmethod
    def protocol_version_mismatch(cls, message: str) -> "AstrBotError":
        """创建协议版本不匹配错误。

        Args:
            message: 详细错误消息

        Returns:
            AstrBotError 实例
        """
        return cls(
            code=ErrorCodes.PROTOCOL_VERSION_MISMATCH,
            message=message,
            hint="请升级 astrbot_sdk 至最新版本",
            retryable=False,
        )

    @classmethod
    def protocol_error(cls, message: str) -> "AstrBotError":
        """创建协议错误。

        Args:
            message: 详细错误消息

        Returns:
            AstrBotError 实例
        """
        return cls(
            code=ErrorCodes.PROTOCOL_ERROR,
            message=message,
            hint="请检查通信双方的协议实现",
            retryable=False,
        )

    @classmethod
    def internal_error(
        cls,
        message: str,
        *,
        hint: str = "请联系插件作者",
    ) -> "AstrBotError":
        """创建内部错误。

        Args:
            message: 详细错误消息
            hint: 用户提示

        Returns:
            AstrBotError 实例
        """
        return cls(
            code=ErrorCodes.INTERNAL_ERROR,
            message=message,
            hint=hint,
            retryable=False,
        )

    def to_payload(self) -> dict[str, object]:
        """序列化为可传输的字典格式。

        用于跨进程传递错误信息。

        Returns:
            包含错误信息的字典
        """
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "retryable": self.retryable,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "AstrBotError":
        """从字典反序列化错误实例。

        Args:
            payload: 包含错误信息的字典

        Returns:
            AstrBotError 实例
        """
        return cls(
            code=str(payload.get("code", ErrorCodes.UNKNOWN_ERROR)),
            message=str(payload.get("message", "未知错误")),
            hint=str(payload.get("hint", "")),
            retryable=bool(payload.get("retryable", False)),
        )
