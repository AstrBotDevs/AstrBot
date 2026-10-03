from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.platform import AstrMessageEvent


class ActiveEventRegistry:
    """维护 unified_msg_origin 到活跃事件的映射。

    用于在 reset 等场景下终止该会话正在处理的事件。
    """

    def __init__(self) -> None:
        self._events: dict[str, set[AstrMessageEvent]] = defaultdict(set)
        self._agent_stop_callbacks: dict[AstrMessageEvent, Callable[[], None]] = {}
        self._background_tasks: dict[
            str, dict[asyncio.Task[None], AstrMessageEvent]
        ] = defaultdict(dict)
        self._background_cancel_requested: set[asyncio.Task[None]] = set()

    def register(self, event: AstrMessageEvent) -> None:
        self._events[event.unified_msg_origin].add(event)

    def unregister(self, event: AstrMessageEvent) -> None:
        umo = event.unified_msg_origin
        self._agent_stop_callbacks.pop(event, None)
        self._events[umo].discard(event)
        if not self._events[umo]:
            del self._events[umo]

    def register_agent_stop_callback(
        self,
        event: AstrMessageEvent,
        callback: Callable[[], None],
    ) -> None:
        """Register immediate Agent cancellation for an active event.

        Args:
            event: Event that owns the active Agent execution.
            callback: Callback that requests cancellation of the active execution.
        """
        self._agent_stop_callbacks[event] = callback

    def unregister_agent_stop_callback(self, event: AstrMessageEvent) -> None:
        """Remove the Agent cancellation callback for an event.

        Args:
            event: Event whose active Agent execution has finished.
        """
        self._agent_stop_callbacks.pop(event, None)

    def get_background_stop_signal(self, event: AstrMessageEvent) -> asyncio.Event:
        """Return the shared stop signal for an event's background execution.

        Repeated calls for the same event reuse its signal, including a signal
        propagated by reference into a background wakeup event. New user events
        have independent signals.

        Args:
            event: Event that owns the background execution.

        Returns:
            The in-memory stop signal shared by the event and its wakeup events.
        """
        signal = event.get_extra("_background_stop_signal")
        if signal is None:
            signal = asyncio.Event()
            event.set_extra("_background_stop_signal", signal)
        if event.get_extra("agent_stop_requested"):
            signal.set()
        return signal

    def register_background_task(
        self,
        event: AstrMessageEvent,
        task: asyncio.Task[None],
    ) -> None:
        """Track a background task independently of its foreground execution.

        The registry retains the task and its owner by unified message origin
        until completion. An already stopped owner causes immediate cancellation.

        Args:
            event: Event that owns the task and its shared stop signal.
            task: Background execution task to retain and remove on completion.

        Returns:
            None.
        """
        if task.done():
            return
        umo = event.unified_msg_origin
        self._background_tasks[umo][task] = event

        def remove_task(done_task: asyncio.Task[None]) -> None:
            tasks = self._background_tasks.get(umo)
            if tasks is not None:
                tasks.pop(done_task, None)
                if not tasks:
                    del self._background_tasks[umo]
            self._background_cancel_requested.discard(done_task)

        task.add_done_callback(remove_task)
        if self.get_background_stop_signal(event).is_set():
            self._background_cancel_requested.add(task)
            task.cancel()

    def stop_all(
        self,
        umo: str,
        exclude: AstrMessageEvent | None = None,
    ) -> int:
        """终止指定 UMO 的所有活跃事件及其后台任务。

        Args:
            umo: 统一消息来源标识符。
            exclude: 需要排除的事件（通常是发起 reset 的事件本身）。

        Returns:
            被终止的事件数量。
        """
        events = set(self._events.get(umo, []))
        events.update(
            event
            for task, event in self._background_tasks.get(umo, {}).items()
            if not task.done()
        )
        for event in events:
            if event is not exclude:
                event.stop_event()
        return self.request_agent_stop_all(umo, exclude)

    def request_agent_stop_all(
        self,
        umo: str,
        exclude: AstrMessageEvent | None = None,
    ) -> int:
        """请求停止指定 UMO 的所有活跃事件中的 Agent 运行。

        与 stop_all 不同，这里不会调用 event.stop_event()，
        因此不会中断事件传播，后续流程（如历史记录保存）仍可继续。

        Args:
            umo: 统一消息来源标识符。
            exclude: 需要排除的事件。

        Returns:
            收到停止请求的事件数量，同一事件只计数一次。
        """
        tasks = self._background_tasks.get(umo, {})
        events = set(self._events.get(umo, []))
        events.update(event for task, event in tasks.items() if not task.done())
        count = 0
        for event in events:
            if event is not exclude:
                event.set_extra("agent_stop_requested", True)
                self.get_background_stop_signal(event).set()
                callback = self._agent_stop_callbacks.get(event)
                if callback:
                    callback()
                count += 1
        for task, event in list(tasks.items()):
            if (
                event is not exclude
                and not task.done()
                and task not in self._background_cancel_requested
            ):
                # 重复停止请求不能打断任务正在执行的取消清理。
                self._background_cancel_requested.add(task)
                task.cancel()
        return count


active_event_registry = ActiveEventRegistry()
