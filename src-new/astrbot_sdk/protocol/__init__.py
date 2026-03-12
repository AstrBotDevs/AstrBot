"""协议模块。

定义 AstrBot SDK 的消息协议和描述符，用于插件与核心之间的通信。
所有消息均使用 Pydantic 定义，确保类型安全和序列化一致性。

架构说明：
    旧版:
        - 使用标准 JSON-RPC 2.0 协议
        - 消息类型较少: Request, SuccessResponse, ErrorResponse
        - 特定请求类型绑定了 AstrMessageEventModel 事件模型
        - 使用 dataclass 和 pydantic 混合定义

    新版:
        - 全新的自描述协议，使用 `type` 字段区分消息类型
        - 更丰富的消息类型: Initialize, Result, Invoke, Event, Cancel
        - 强大的描述符系统: HandlerDescriptor, CapabilityDescriptor
        - 多种触发器类型: Command, Message, Event, Schedule
        - 纯 Pydantic 定义，支持严格验证
        - 提供 LegacyAdapter 实现新旧协议互操作

协议消息流程：
    1. Initialize: 握手建立连接，交换能力和处理器信息
    2. Invoke: 调用远程能力
    3. Event: 流式事件通知 (started/delta/completed/failed)
    4. Result: 调用结果返回
    5. Cancel: 取消正在进行的调用

与旧版对比：
    旧版 JSON-RPC 消息:
        {
            "jsonrpc": "2.0",
            "id": "xxx",
            "method": "call_handler",
            "params": {"handler_full_name": "...", "event": {...}}
        }

    新版协议消息:
        {
            "type": "invoke",
            "id": "xxx",
            "capability": "handler.invoke",
            "input": {"handler_id": "...", "event": {...}}
        }

TODO: (功能完善):
    - 添加消息签名验证支持，确保消息来源可信
    - 添加消息压缩支持，减少大数据传输开销
    - 添加批量消息支持 (BatchMessage)，提高传输效率
    - 添加消息追踪 ID (trace_id) 支持，便于日志关联
    - CapabilityDescriptor 缺少 rate_limit 限流配置
    - HandlerDescriptor 缺少 timeout 超时配置
    - 缺少心跳消息 (HeartbeatMessage) 支持
    - 缺少健康检查消息 (HealthCheckMessage) 支持
"""

from .descriptors import CapabilityDescriptor, HandlerDescriptor, Permissions
from .messages import (
    CancelMessage,
    EventMessage,
    InitializeMessage,
    InitializeOutput,
    InvokeMessage,
    ResultMessage,
)

__all__ = [
    "CapabilityDescriptor",
    "CancelMessage",
    "EventMessage",
    "HandlerDescriptor",
    "InitializeMessage",
    "InitializeOutput",
    "InvokeMessage",
    "Permissions",
    "ResultMessage",
]
