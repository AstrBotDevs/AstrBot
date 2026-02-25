from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.platform import AstrMessageEvent


class ActiveEventRegistry:
    """维护 unified_msg_origin 到活跃事件的映射。

    用于在 reset 等场景下终止该会话正在处理的事件。
    """

    def __init__(self) -> None:
        self._events: dict[str, set[AstrMessageEvent]] = defaultdict(set)

    def register(self, event: AstrMessageEvent) -> None:
        self._events[event.unified_msg_origin].add(event)

    def unregister(self, event: AstrMessageEvent) -> None:
        umo = event.unified_msg_origin
        self._events[umo].discard(event)
        if not self._events[umo]:
            del self._events[umo]

    def stop_all(
        self,
        umo: str,
        exclude: AstrMessageEvent | None = None,
    ) -> int:
        """终止指定 UMO 的所有活跃事件。

        Args:
            umo: 统一消息来源标识符。
            exclude: 需要排除的事件（通常是发起 reset 的事件本身）。

        Returns:
            被终止的事件数量。
        """
        count = 0
        for event in list(self._events.get(umo, [])):
            if event is not exclude:
                event.stop_event()
                count += 1
        return count

    def request_agent_stop_all(
        self,
        umo: str,
        exclude: AstrMessageEvent | None = None,
    ) -> int:
        """请求停止指定 UMO 的所有活跃事件中的 Agent 运行。

        与 stop_all 不同，这里不会调用 event.stop_event()，
        因此不会中断事件传播，后续流程（如历史记录保存）仍可继续。
        """
        count = 0
        for event in list(self._events.get(umo, [])):
            if event is not exclude:
                event.set_extra("agent_stop_requested", True)
                count += 1
        return count


active_event_registry = ActiveEventRegistry()
