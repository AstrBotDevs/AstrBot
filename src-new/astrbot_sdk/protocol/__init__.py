"""AstrBot v4 协议公共入口。

这里暴露 v4 原生协议的消息模型、描述符和解析函数。

握手阶段由 `InitializeMessage` 发起，返回值不是另一条 initialize 消息，而是
`ResultMessage(kind="initialize_result")`，其 `output` 负载可解析为
`InitializeOutput`。
"""

from .descriptors import (
    CapabilityDescriptor,
    CommandRouteSpec,
    CommandTrigger,
    CompositeFilterSpec,
    EventTrigger,
    FilterSpec,
    HandlerDescriptor,
    LocalFilterRefSpec,
    MessageTrigger,
    MessageTypeFilterSpec,
    ParamSpec,
    Permissions,
    PlatformFilterSpec,
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
    "CommandRouteSpec",
    "CommandTrigger",
    "CancelMessage",
    "CompositeFilterSpec",
    "ErrorPayload",
    "EventTrigger",
    "EventMessage",
    "FilterSpec",
    "HandlerDescriptor",
    "InitializeMessage",
    "InitializeOutput",
    "InvokeMessage",
    "LocalFilterRefSpec",
    "MessageTrigger",
    "MessageTypeFilterSpec",
    "ParamSpec",
    "PeerInfo",
    "PlatformFilterSpec",
    "Permissions",
    "ProtocolMessage",
    "ResultMessage",
    "ScheduleTrigger",
    "SessionRef",
    "Trigger",
    "parse_message",
]
