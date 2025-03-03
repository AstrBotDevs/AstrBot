from __future__ import annotations
import enum
import heapq
from dataclasses import dataclass, field
from typing import Awaitable, List, Dict, TypeVar, Generic
from .filter import HandlerFilter
from .star import star_map

T = TypeVar("T", bound="StarHandlerMetadata")


class StarHandlerRegistry(Generic[T]):
    """用于存储所有的 Star Handler"""

    star_handlers_map: Dict[str, StarHandlerMetadata] = {}
    """用于快速查找。key 是 handler_full_name"""
    _handlers = []

    def append(self, handler: StarHandlerMetadata):
        """添加一个 Handler"""
        if "priority" not in handler.extras_configs:
            handler.extras_configs["priority"] = 0

        heapq.heappush(self._handlers, (-handler.extras_configs["priority"], handler))
        self.star_handlers_map[handler.handler_full_name] = handler

    def _print_handlers(self):
        """打印所有的 Handler"""
        for _, handler in self._handlers:
            print(handler.handler_full_name)

    def get_handlers_by_event_type(
        self, event_type: EventType, only_activated=True
    ) -> List[StarHandlerMetadata]:
        """通过事件类型获取 Handler"""
        handlers = [
            handler
            for _, handler in self._handlers
            if handler.event_type == event_type
            and (
                not only_activated
                or (
                    star_map[handler.handler_module_path]
                    and star_map[handler.handler_module_path].activated
                )
            )
        ]
        return handlers

    def get_handler_by_full_name(self, full_name: str) -> StarHandlerMetadata:
        """通过 Handler 的全名获取 Handler"""
        return self.star_handlers_map.get(full_name, None)

    def get_handlers_by_module_name(
        self, module_name: str
    ) -> List[StarHandlerMetadata]:
        """通过模块名获取 Handler"""
        return [
            handler
            for _, handler in self._handlers
            if handler.handler_module_path == module_name
        ]

    def clear(self):
        """清空所有的 Handler"""
        self.star_handlers_map.clear()
        self._handlers.clear()

    def remove(self, handler: StarHandlerMetadata):
        """删除一个 Handler"""
        # self._handlers.remove(handler)
        for i, h in enumerate(self._handlers):
            if h[1] == handler:
                self._handlers.pop(i)
                break
        try:
            del self.star_handlers_map[handler.handler_full_name]
        except KeyError:
            pass

    def __iter__(self):
        """使 StarHandlerRegistry 支持迭代"""
        return (handler for _, handler in self._handlers)

    def __len__(self):
        """返回 Handler 的数量"""
        return len(self._handlers)


star_handlers_registry = StarHandlerRegistry()


class EventType(enum.Enum):
    """表示一个 AstrBot 内部事件的类型。如适配器消息事件、LLM 请求事件、发送消息前的事件等

    用于对 Handler 的职能分组。
    """

    OnAstrBotLoadedEvent = enum.auto()  # AstrBot 加载完成

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

    handler: Awaitable
    """Handler 的函数对象，应当是一个异步函数"""

    event_filters: List[HandlerFilter]
    """一个适配器消息事件过滤器，用于描述这个 Handler 能够处理、应该处理的适配器消息事件"""

    desc: str = ""
    """Handler 的描述信息"""

    extras_configs: dict = field(default_factory=dict)
    """插件注册的一些其他的信息, 如 priority 等"""

    def __lt__(self, other: StarHandlerMetadata):
        """定义小于运算符以支持优先队列"""
        return self.extras_configs.get("priority", 0) < other.extras_configs.get(
            "priority", 0
        )
