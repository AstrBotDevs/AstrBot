"""v4 协议消息模型。

这些模型描述的是 `Peer` 与 `Peer` 之间的线协议。握手阶段通过
`InitializeMessage` 发起，再由 `ResultMessage(kind="initialize_result")`
返回 `InitializeOutput`；能力调用阶段则使用 `InvokeMessage` / `ResultMessage`
或 `EventMessage` 序列。
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .descriptors import CapabilityDescriptor, HandlerDescriptor


class _MessageBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorPayload(_MessageBase):
    """错误载荷，用于 ResultMessage 和 EventMessage 中传递错误信息。

    与旧版 JSON-RPC 错误对比：
        旧版: code 为整数，如 -32000
        新版: code 为字符串，如 "internal_error"

    Attributes:
        code: 错误码，字符串类型，便于语义化错误分类
        message: 错误消息，人类可读的错误描述
        hint: 错误提示，可选的解决方案或建议
        retryable: 是否可重试，标识该错误是否可通过重试解决
    """

    code: str
    message: str
    hint: str = ""
    retryable: bool = False


class PeerInfo(_MessageBase):
    """对等节点信息，标识消息发送方的身份。

    与旧版对比：
        旧版: 通过 handshake params 中的 plugin_name 隐式传递
        新版: 显式的 PeerInfo 结构，支持 plugin 和 core 两种角色

    Attributes:
        name: 节点名称，通常是插件 ID 或核心标识
        role: 节点角色，"plugin" 或 "core"
        version: 节点版本号，可选
    """

    name: str
    role: Literal["plugin", "core"]
    version: str | None = None


class InitializeMessage(_MessageBase):
    """初始化消息，用于建立连接时交换信息。

    与旧版 JSON-RPC handshake 对比：
        旧版:
            {
                "jsonrpc": "2.0",
                "id": "xxx",
                "method": "handshake",
                "params": {}
            }
            响应包含插件元信息和处理器列表

        新版:
            {
                "type": "initialize",
                "id": "xxx",
                "protocol_version": "1.0",
                "peer": {"name": "...", "role": "plugin", "version": "..."},
                "handlers": [...],
                "metadata": {...}
            }

    Attributes:
        type: 消息类型，固定为 "initialize"
        id: 消息 ID，用于关联响应
        protocol_version: 协议版本号
        peer: 发送方节点信息
        handlers: 注册的处理器描述符列表
        metadata: 扩展元数据，可存储插件配置等信息
    """

    type: Literal["initialize"] = "initialize"
    id: str
    protocol_version: str
    peer: PeerInfo
    handlers: list[HandlerDescriptor] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InitializeOutput(_MessageBase):
    """初始化输出，作为 InitializeMessage 的响应数据。

    与旧版对比：
        旧版: handshake 响应中包含完整的插件信息
        新版: 仅返回对等方信息和能力列表，更简洁

    Attributes:
        peer: 接收方（核心）节点信息
        capabilities: 核心提供的能力描述符列表
        metadata: 扩展元数据
    """

    peer: PeerInfo
    capabilities: list[CapabilityDescriptor] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResultMessage(_MessageBase):
    """结果消息，用于返回能力调用的结果。

    与旧版 JSON-RPC 响应对比：
        旧版成功响应:
            {"jsonrpc": "2.0", "id": "xxx", "result": {...}}
        旧版错误响应:
            {"jsonrpc": "2.0", "id": "xxx", "error": {"code": -32000, "message": "..."}}

        新版成功结果:
            {"type": "result", "id": "xxx", "success": true, "output": {...}}
        新版失败结果:
            {"type": "result", "id": "xxx", "success": false, "error": {...}}

    Attributes:
        type: 消息类型，固定为 "result"
        id: 关联的请求 ID
        kind: 结果类型，可选，如 "initialize_result" 标识初始化结果
        success: 是否成功
        output: 成功时的输出数据
        error: 失败时的错误信息
    """

    type: Literal["result"] = "result"
    id: str
    kind: str | None = None
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: ErrorPayload | None = None

    @model_validator(mode="after")
    def validate_result_state(self) -> "ResultMessage":
        """约束 success / output / error 的组合状态。"""
        if self.success:
            if self.error is not None:
                raise ValueError("success=true 时 error 必须为空")
            return self
        if self.error is None:
            raise ValueError("success=false 时必须提供 error")
        if self.output:
            raise ValueError("success=false 时 output 必须为空")
        return self


class InvokeMessage(_MessageBase):
    """调用消息，用于请求执行远程能力。

    与旧版 JSON-RPC 请求对比：
        旧版:
            {
                "jsonrpc": "2.0",
                "id": "xxx",
                "method": "call_handler",
                "params": {"handler_full_name": "...", "event": {...}}
            }

        新版:
            {
                "type": "invoke",
                "id": "xxx",
                "capability": "handler.invoke",
                "input": {"handler_id": "...", "event": {...}},
                "stream": false
            }

    Attributes:
        type: 消息类型，固定为 "invoke"
        id: 请求 ID，用于关联响应
        capability: 目标能力名称，格式为 "namespace.action"
        input: 调用输入参数
        stream: 是否期望流式响应，若为 True 将收到 EventMessage 序列
    """

    type: Literal["invoke"] = "invoke"
    id: str
    capability: str
    input: dict[str, Any] = Field(default_factory=dict)
    stream: bool = False


class EventMessage(_MessageBase):
    """事件消息，用于流式调用的状态通知。

    流式调用生命周期：
        1. started: 调用开始，所有字段为空
        2. delta: 数据增量更新，包含 data 字段
        3. completed: 调用完成，包含 output 字段
        4. failed: 调用失败，包含 error 字段

    与旧版 JSON-RPC 通知对比：
        旧版使用独立的 method 区分：
            - handler_stream_start
            - handler_stream_update
            - handler_stream_end

        新版使用统一的 EventMessage，通过 phase 字段区分：
            {"type": "event", "id": "xxx", "phase": "delta", "data": {...}}

    Attributes:
        type: 消息类型，固定为 "event"
        id: 关联的请求 ID
        phase: 事件阶段，started/delta/completed/failed
        data: 增量数据，仅 delta 阶段有效
        output: 最终输出，仅 completed 阶段有效
        error: 错误信息，仅 failed 阶段有效
    """

    type: Literal["event"] = "event"
    id: str
    phase: Literal["started", "delta", "completed", "failed"]
    data: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: ErrorPayload | None = None

    @model_validator(mode="after")
    def validate_phase_constraints(self) -> "EventMessage":
        """验证各 phase 的字段约束。

        - started: 所有字段必须为空
        - delta: 必须有 data，output/error 必须为空
        - completed: 必须有 output，data/error 必须为空
        - failed: 必须有 error，data/output 必须为空
        """
        phase = self.phase
        if phase == "started":
            if self.data or self.output or self.error:
                raise ValueError("started phase 必须所有字段为空")
        elif phase == "delta":
            if not self.data:
                raise ValueError("delta phase 需要 data")
            if self.output or self.error:
                raise ValueError("delta phase 的 output/error 必须为空")
        elif phase == "completed":
            if not self.output:
                raise ValueError("completed phase 需要 output")
            if self.data or self.error:
                raise ValueError("completed phase 的 data/error 必须为空")
        elif phase == "failed":
            if self.error is None:
                raise ValueError("failed phase 需要 error")
            if self.data or self.output:
                raise ValueError("failed phase 的 data/output 必须为空")
        return self


class CancelMessage(_MessageBase):
    """取消消息，用于取消正在进行的调用。

    与旧版对比：
        旧版: 使用 {"jsonrpc": "2.0", "method": "cancel", "params": {"reason": "..."}}
        新版: 专门的 CancelMessage 类型，语义更明确

    Attributes:
        type: 消息类型，固定为 "cancel"
        id: 要取消的请求 ID
        reason: 取消原因，默认为 "user_cancelled"
    """

    type: Literal["cancel"] = "cancel"
    id: str
    reason: str = "user_cancelled"


ProtocolMessage = (
    InitializeMessage | ResultMessage | InvokeMessage | EventMessage | CancelMessage
)
"""协议消息联合类型，所有有效消息类型的联合。"""

_PROTOCOL_MESSAGE_MODELS = {
    "initialize": InitializeMessage,
    "result": ResultMessage,
    "invoke": InvokeMessage,
    "event": EventMessage,
    "cancel": CancelMessage,
}


def parse_message(
    payload: ProtocolMessage | str | bytes | dict[str, Any],
) -> ProtocolMessage:
    """解析协议消息。

    从原始载荷（字符串、字节或字典）解析为对应的 ProtocolMessage 类型。
    根据 "type" 字段自动识别消息类型并验证。

    Args:
        payload: 原始消息载荷，支持已解析模型、JSON 字符串、字节或字典

    Returns:
        解析后的协议消息对象

    Raises:
        ValueError: 未知的消息类型

    Example:
        >>> msg = parse_message('{"type": "invoke", "id": "1", "capability": "test"}')
        >>> isinstance(msg, InvokeMessage)
        True
    """
    if isinstance(
        payload,
        (
            InitializeMessage,
            ResultMessage,
            InvokeMessage,
            EventMessage,
            CancelMessage,
        ),
    ):
        return payload
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("协议消息必须是 JSON object")
    message_type = payload.get("type")
    model = _PROTOCOL_MESSAGE_MODELS.get(str(message_type))
    if model is not None:
        return model.model_validate(payload)
    raise ValueError(f"未知消息类型：{message_type}")


__all__ = [
    "CancelMessage",
    "ErrorPayload",
    "EventMessage",
    "InitializeMessage",
    "InitializeOutput",
    "InvokeMessage",
    "PeerInfo",
    "ProtocolMessage",
    "ResultMessage",
    "parse_message",
]
