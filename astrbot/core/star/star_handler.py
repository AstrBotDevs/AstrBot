from __future__ import annotations
import enum
from dataclasses import dataclass, field
from typing import Awaitable, List, Dict, TypeVar, Generic
from .filter import HandlerFilter
from .star import star_map

T = TypeVar("T", bound="StarHandlerMetadata")

class StarHandlerRegistry(Generic[T]):
    def __init__(self):
        self.star_handlers_map: Dict[str, StarHandlerMetadata] = {}
        self._handlers: List[StarHandlerMetadata] = []

    def append(self, handler: StarHandlerMetadata):
        """添加一个 Handler，并保持按优先级有序"""
        if "priority" not in handler.extras_configs:
            handler.extras_configs["priority"] = 0

        self.star_handlers_map[handler.handler_full_name] = handler
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: -h.extras_configs["priority"])

    def _print_handlers(self):
        for handler in self._handlers:
            print(handler.handler_full_name)

    def get_handlers_by_event_type(
        self, event_type: EventType, only_activated=True, platform_id=None
    ) -> List[StarHandlerMetadata]:
        handlers = []
        for handler in self._handlers:
            if handler.event_type != event_type:
                continue
            if only_activated:
                plugin = star_map.get(handler.handler_module_path)
                if not (plugin and plugin.activated):
                    continue
            if platform_id and event_type != EventType.OnAstrBotLoadedEvent:
                if not handler.is_enabled_for_platform(platform_id):
                    continue
            handlers.append(handler)
        return handlers

    def get_handler_by_full_name(self, full_name: str) -> StarHandlerMetadata:
        return self.star_handlers_map.get(full_name, None)

    def get_handlers_by_module_name(
        self, module_name: str
    ) -> List[StarHandlerMetadata]:
        return [
            handler for handler in self._handlers
            if handler.handler_module_path == module_name
        ]

    def clear(self):
        self.star_handlers_map.clear()
        self._handlers.clear()

    def remove(self, handler: StarHandlerMetadata):
        self.star_handlers_map.pop(handler.handler_full_name, None)
        self._handlers = [h for h in self._handlers if h != handler]

    def __iter__(self):
        return iter(self._handlers)

    def __len__(self):
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

    def is_enabled_for_platform(self, platform_id: str) -> bool:
        """检查插件是否在指定平台启用

        Args:
            platform_id: 平台ID，这是从event.get_platform_id()获取的，用于唯一标识平台实例

        Returns:
            bool: 是否启用，True表示启用，False表示禁用
        """
        plugin = star_map.get(self.handler_module_path)

        # 如果插件元数据不存在，默认允许执行
        if not plugin or not plugin.name:
            return True

        # 先检查插件是否被激活
        if not plugin.activated:
            return False

        # 直接使用StarMetadata中缓存的supported_platforms判断平台兼容性
        if (
            hasattr(plugin, "supported_platforms")
            and platform_id in plugin.supported_platforms
        ):
            return plugin.supported_platforms[platform_id]

        # 如果没有缓存数据，默认允许执行
        return True
