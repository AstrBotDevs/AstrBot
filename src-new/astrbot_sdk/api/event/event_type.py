"""旧版事件类型兼容枚举。"""

from __future__ import annotations

import enum


class EventType(enum.Enum):
    OnAstrBotLoadedEvent = enum.auto()
    OnPlatformLoadedEvent = enum.auto()
    AdapterMessageEvent = enum.auto()
    OnLLMRequestEvent = enum.auto()
    OnLLMResponseEvent = enum.auto()
    OnDecoratingResultEvent = enum.auto()
    OnCallingFuncToolEvent = enum.auto()
    OnAfterMessageSentEvent = enum.auto()
