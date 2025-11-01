from __future__ import annotations

import enum
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from .filter import HandlerFilter
from .star import star_map

T = TypeVar("T", bound="StarHandlerMetadata")


class StarHandlerRegistry(Generic[T]):
    def __init__(self):
        self.star_handlers_map: dict[str, StarHandlerMetadata] = {}
        self._handlers: list[StarHandlerMetadata] = []

    def append(self, handler: StarHandlerMetadata):
        """添加一个 Handler，并保持按优先级有序

        时间复杂度: O(n log n)，其中 n 是已注册的 handler 数量
        - 字典插入: O(1)
        - 列表追加: O(1) 摊销
        - 列表排序: O(n log n)
        空间复杂度: O(1)，不包括存储 handler 本身的空间
        """
        if "priority" not in handler.extras_configs:
            handler.extras_configs["priority"] = 0

        self.star_handlers_map[handler.handler_full_name] = handler
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: -h.extras_configs["priority"])

    def _print_handlers(self):
        for handler in self._handlers:
            print(handler.handler_full_name)

    def get_handlers_by_event_type(
        self,
        event_type: EventType,
        only_activated=True,
        plugins_name: list[str] | None = None,
    ) -> list[StarHandlerMetadata]:
        """按事件类型获取符合条件的 handlers

        时间复杂度: O(n * m)，其中 n 是 handler 数量，m 是插件白名单长度
        - 遍历所有 handlers: O(n)
        - 每次迭代中的字典查找: O(1)
        - 白名单检查 (plugins_name not in): O(m)
        空间复杂度: O(k)，其中 k 是符合条件的 handler 数量
        """
        handlers = []
        for handler in self._handlers:
            # 过滤事件类型
            if handler.event_type != event_type:
                continue
            # 过滤启用状态
            if only_activated:
                plugin = star_map.get(handler.handler_module_path)
                if not (plugin and plugin.activated):
                    continue
            # 过滤插件白名单
            if plugins_name is not None and plugins_name != ["*"]:
                plugin = star_map.get(handler.handler_module_path)
                if not plugin:
                    continue
                if (
                    plugin.name not in plugins_name
                    and event_type
                    not in (
                        EventType.OnAstrBotLoadedEvent,
                        EventType.OnPlatformLoadedEvent,
                    )
                    and not plugin.reserved
                ):
                    continue
            handlers.append(handler)
        return handlers

    def get_handler_by_full_name(self, full_name: str) -> StarHandlerMetadata | None:
        """通过完整名称获取 handler

        时间复杂度: O(1)，字典查找
        空间复杂度: O(1)
        """
        return self.star_handlers_map.get(full_name, None)

    def get_handlers_by_module_name(
        self,
        module_name: str,
    ) -> list[StarHandlerMetadata]:
        """通过模块名称获取所有 handlers

        时间复杂度: O(n)，其中 n 是 handler 总数，需要遍历所有 handler
        空间复杂度: O(k)，其中 k 是匹配的 handler 数量
        """
        return [
            handler
            for handler in self._handlers
            if handler.handler_module_path == module_name
        ]

    def clear(self):
        """清空所有 handlers

        时间复杂度: O(n)，其中 n 是 handler 数量，需要清理所有引用
        空间复杂度: O(1)
        """
        self.star_handlers_map.clear()
        self._handlers.clear()

    def remove(self, handler: StarHandlerMetadata):
        """移除指定的 handler

        时间复杂度: O(n)，其中 n 是 handler 数量
        - 字典删除: O(1)
        - 列表过滤重建: O(n)
        空间复杂度: O(n)，需要创建新的列表
        """
        self.star_handlers_map.pop(handler.handler_full_name, None)
        self._handlers = [h for h in self._handlers if h != handler]

    def __iter__(self):
        return iter(self._handlers)

    def __len__(self):
        return len(self._handlers)


star_handlers_registry = StarHandlerRegistry()  # type: ignore


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


@dataclass
class StarHandlerMetadata:
    """描述一个 Star 所注册的某一个 Handler。"""

    event_type: EventType
    """Handler 的事件类型"""

    handler_full_name: str
    '''格式为 f"{handler.__module__}_{handler.__name__}"'''

    handler_name: str
    """Handler 的名字，也就是方法名"""

    handler_module_path: str
    """Handler 所在的模块路径。"""

    handler: Callable[..., Awaitable[Any]]
    """Handler 的函数对象，应当是一个异步函数"""

    event_filters: list[HandlerFilter]
    """一个适配器消息事件过滤器，用于描述这个 Handler 能够处理、应该处理的适配器消息事件"""

    desc: str = ""
    """Handler 的描述信息"""

    extras_configs: dict = field(default_factory=dict)
    """插件注册的一些其他的信息, 如 priority 等"""

    def __lt__(self, other: StarHandlerMetadata):
        """定义小于运算符以支持优先队列"""
        return self.extras_configs.get("priority", 0) < other.extras_configs.get(
            "priority",
            0,
        )
