from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class ActiveEventControl(Protocol):
    """Narrow control port for active event cancellation."""

    def stop_all(
        self,
        umo: str,
        exclude: AstrMessageEvent | None = None,
    ) -> int: ...

    def request_agent_stop_all(
        self,
        umo: str,
        exclude: AstrMessageEvent | None = None,
    ) -> int: ...


class ActiveEventRegistry:
    """维护 unified_msg_origin 到活跃事件的映射。

    用于在 reset 等场景下终止该会话正在处理的事件。
    """

    def __init__(self) -> None:
        self._events: dict[str, set[AstrMessageEvent]] = defaultdict(set)
        self._agent_stop_callbacks: dict[
            AstrMessageEvent, set[Callable[[], object]]
        ] = defaultdict(set)

    def register(self, event: AstrMessageEvent) -> None:
        self._events[event.unified_msg_origin].add(event)

    def unregister(self, event: AstrMessageEvent) -> None:
        umo = event.unified_msg_origin
        self._events[umo].discard(event)
        if not self._events[umo]:
            del self._events[umo]
        self._agent_stop_callbacks.pop(event, None)

    def register_agent_stop_callback(
        self,
        event: AstrMessageEvent,
        callback: Callable[[], object],
    ) -> None:
        """Register the current runner's stop callback for one active event."""
        self._agent_stop_callbacks[event].add(callback)

    def unregister_agent_stop_callback(
        self,
        event: AstrMessageEvent,
        callback: Callable[[], object],
    ) -> None:
        """Remove a runner stop callback after its lifecycle has ended."""
        callbacks = self._agent_stop_callbacks.get(event)
        if callbacks is None:
            return
        callbacks.discard(callback)
        if not callbacks:
            self._agent_stop_callbacks.pop(event, None)

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
                for callback in tuple(self._agent_stop_callbacks.get(event, ())):
                    try:
                        callback()
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "Failed to stop active Agent for %s: %s",
                            umo,
                            safe_error("", exc),
                        )
                count += 1
        return count
