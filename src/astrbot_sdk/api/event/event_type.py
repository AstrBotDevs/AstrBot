from __future__ import annotations
import enum


class EventType(enum.Enum):
    """表示一个 AstrBot 内部事件的类型。如适配器消息事件、LLM 请求事件、发送消息前的事件等

    用于对 Handler 的职能分组。
    """

    OnAstrBotLoadedEvent = enum.auto()  # AstrBot 加载完成
    OnPlatformLoadedEvent = enum.auto()  # 平台加载完成

    AdapterMessageEvent = enum.auto()  # 收到适配器发来的消息
    OnLLMRequestEvent = enum.auto()  # 收到 LLM 请求（可以是用户也可以是插件）
    OnLLMResponseEvent = enum.auto()  # LLM 响应后
    OnDecoratingResultEvent = enum.auto()  # 发送消息前
    OnCallingFuncToolEvent = enum.auto()  # 调用函数工具
    OnAfterMessageSentEvent = enum.auto()  # 发送消息后
