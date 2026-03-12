"""AstrBot v4 协议公共入口。

这里暴露的是协议层的公共模型和 legacy 适配入口。需要区分两件事：

1. v4 原生协议:
   `InitializeMessage` / `InvokeMessage` / `ResultMessage` / `EventMessage`
2. legacy JSON-RPC 兼容:
   `LegacyAdapter` 及其若干便捷转换函数

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
from .legacy_adapter import (
    LEGACY_ADAPTER_MESSAGE_EVENT,
    LEGACY_CONTEXT_CAPABILITY,
    LEGACY_HANDSHAKE_METADATA_KEY,
    LEGACY_JSONRPC_VERSION,
    LEGACY_PLUGIN_KEYS_METADATA_KEY,
    LegacyAdapter,
    LegacyErrorData,
    LegacyErrorResponse,
    LegacyMessage,
    LegacyRequest,
    LegacySuccessResponse,
    LegacyToV4Message,
    cancel_to_legacy_request,
    event_to_legacy_notification,
    initialize_to_legacy_handshake_response,
    invoke_to_legacy_request,
    legacy_message_to_v4,
    legacy_request_to_invoke,
    legacy_response_to_message,
    parse_legacy_message,
    result_to_legacy_response,
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
    "LEGACY_ADAPTER_MESSAGE_EVENT",
    "LEGACY_CONTEXT_CAPABILITY",
    "LEGACY_HANDSHAKE_METADATA_KEY",
    "LEGACY_JSONRPC_VERSION",
    "LEGACY_PLUGIN_KEYS_METADATA_KEY",
    "LegacyAdapter",
    "LegacyErrorData",
    "LegacyErrorResponse",
    "LegacyMessage",
    "LegacyRequest",
    "LegacySuccessResponse",
    "LegacyToV4Message",
    "MessageTrigger",
    "PeerInfo",
    "Permissions",
    "ProtocolMessage",
    "ResultMessage",
    "ScheduleTrigger",
    "SessionRef",
    "Trigger",
    "cancel_to_legacy_request",
    "event_to_legacy_notification",
    "initialize_to_legacy_handshake_response",
    "invoke_to_legacy_request",
    "legacy_message_to_v4",
    "legacy_request_to_invoke",
    "legacy_response_to_message",
    "parse_legacy_message",
    "parse_message",
    "result_to_legacy_response",
]
