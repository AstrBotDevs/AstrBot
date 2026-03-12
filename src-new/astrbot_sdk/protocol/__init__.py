"""AstrBot v4 协议公共入口。

这里优先暴露 v4 原生协议的消息模型、描述符和解析函数。
legacy JSON-RPC 兼容保留在 `astrbot_sdk.protocol.legacy_adapter` 子模块中，
供迁移和适配场景显式使用，而不是作为主协议根入口的一部分。

握手阶段由 `InitializeMessage` 发起，返回值不是另一条 initialize 消息，而是
`ResultMessage(kind="initialize_result")`，其 `output` 负载可解析为
`InitializeOutput`。
"""

from .descriptors import (
    CapabilityDescriptor,
    CommandTrigger,
    EventTrigger,
    HandlerDescriptor,
    MessageTrigger,
    Permissions,
    ScheduleTrigger,
    SessionRef,
    Trigger,
)
from .messages import (
    CancelMessage,
    ErrorPayload,
    EventMessage,
    InitializeMessage,
    InitializeOutput,
    InvokeMessage,
    PeerInfo,
    ProtocolMessage,
    ResultMessage,
    parse_message,
)

__all__ = [
    "CapabilityDescriptor",
    "CommandTrigger",
    "CancelMessage",
    "ErrorPayload",
    "EventTrigger",
    "EventMessage",
    "HandlerDescriptor",
    "InitializeMessage",
    "InitializeOutput",
    "InvokeMessage",
    "MessageTrigger",
    "PeerInfo",
    "Permissions",
    "ProtocolMessage",
    "ResultMessage",
    "ScheduleTrigger",
    "SessionRef",
    "Trigger",
    "parse_message",
]
