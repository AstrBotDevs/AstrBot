"""Bounded inbound turn windows for optional DM coalescing."""

from __future__ import annotations

import asyncio
import copy
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field

from astrbot import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.task_utils import cancel_tracked_tasks, create_tracked_task

from .turn_router import MANAGER_FLUSH_SENTINEL, MANAGER_FLUSH_TOKEN

DEFAULT_MAX_WINDOWS = 256
DEFAULT_MAX_FRAGMENTS = 32
DEFAULT_MAX_TYPING = 256


@dataclass(slots=True)
class TurnWindow:
    """Buffered fragments for one inbound turn."""

    key: str
    fragments: list[AstrMessageEvent] = field(default_factory=list)
    opened_at: float = 0.0
    wait_seconds: float = 2.0
    max_total_seconds: float = 12.0
    typing_key: str = ""
    flush_task: asyncio.Task | None = None
    typing_paused: bool = False


class TurnWindowManager:
    """Own bounded buffers, flush timers, and typing pause state."""

    def __init__(
        self,
        enqueue: Callable[[AstrMessageEvent], bool],
        *,
        max_windows: int = DEFAULT_MAX_WINDOWS,
        max_fragments: int = DEFAULT_MAX_FRAGMENTS,
        max_typing: int = DEFAULT_MAX_TYPING,
        max_typing_wait: float = 30.0,
    ) -> None:
        self._enqueue = enqueue
        self._max_windows = max(1, max_windows)
        self._max_fragments = max(1, max_fragments)
        self._max_typing = max(1, max_typing)
        self.max_typing_wait = max(0.0, max_typing_wait)
        self._windows: OrderedDict[str, TurnWindow] = OrderedDict()
        self._typing: OrderedDict[str, float] = OrderedDict()
        self._typing_tasks: dict[str, asyncio.Task] = {}
        self._tasks: set[asyncio.Task] = set()
        self._loop = asyncio.get_event_loop()

    def window_key(self, event: AstrMessageEvent, *, group: bool = False) -> str:
        """Return the coalesce key for an event.

        Args:
            event: Inbound event.
            group: When true, include sender identity.
        """
        umo = getattr(event, "unified_msg_origin", "") or event.get_session_id()
        if group:
            return f"{umo}:{event.get_sender_id()}"
        return str(umo)

    def has_open_window(self, key: str) -> bool:
        """Return whether a window is currently buffering."""
        return key in self._windows

    def typing_key(self, event: AstrMessageEvent) -> str:
        """Return the adapter-side typing identity for an inbound event."""
        return ":".join(
            (
                str(event.get_platform_id()),
                str(event.unified_msg_origin),
                str(event.get_sender_id()),
            )
        )

    def set_max_typing_wait(self, value: float) -> None:
        """Update the guard used for future typing pauses."""
        self.max_typing_wait = max(0.0, float(value))

    def accept(
        self,
        event: AstrMessageEvent,
        *,
        wait_seconds: float,
        max_total_seconds: float,
        group: bool = False,
    ) -> None:
        """Buffer a should_run_llm fragment and (re)arm the flush timer."""
        key = self.window_key(event, group=group)
        window = self._windows.get(key)
        if window is None:
            self._evict_oldest_window()
            window = TurnWindow(
                key=key,
                opened_at=self._loop.time(),
                wait_seconds=wait_seconds,
                max_total_seconds=max_total_seconds,
                typing_key=self.typing_key(event),
                typing_paused=self.typing_key(event) in self._typing,
            )
            self._windows[key] = window
        if len(window.fragments) >= self._max_fragments:
            dropped = window.fragments.pop(0)
            logger.warning("Turn window %s dropped oldest fragment", key)
            dropped.cleanup_temporary_local_files()
        window.fragments.append(event)
        self._arm_flush(window)

    def discard(self, event: AstrMessageEvent, *, group: bool = False) -> None:
        """Drop an open window without flushing to the LLM."""
        key = self.window_key(event, group=group)
        window = self._windows.pop(key, None)
        if window is None:
            return
        self._cancel_window_task(window)
        for fragment in window.fragments:
            fragment.cleanup_temporary_local_files()
        logger.info("Discarded turn window %s on command", key)

    def recall(self, message_id: str) -> None:
        """Remove a buffered fragment by message id and drop empty windows."""
        empty: list[str] = []
        target_id = str(message_id)
        for key, window in self._windows.items():
            kept: list[AstrMessageEvent] = []
            for fragment in window.fragments:
                if str(getattr(fragment.message_obj, "message_id", "")) == target_id:
                    fragment.cleanup_temporary_local_files()
                else:
                    kept.append(fragment)
            window.fragments = kept
            if not window.fragments:
                empty.append(key)
        for key in empty:
            window = self._windows.pop(key)
            self._cancel_window_task(window)

    def pause_typing(self, typing_key: str) -> None:
        """Pause flush for a typing-start notice."""
        if typing_key in self._typing:
            return
        self._evict_oldest_typing()
        self._typing[typing_key] = self._loop.time()
        for window in self._windows.values():
            if window.typing_key == typing_key:
                window.typing_paused = True
                self._cancel_window_task(window)
        self._typing_tasks[typing_key] = create_tracked_task(
            self._tasks,
            self._resume_typing_after_guard(typing_key),
            name=f"turn-typing-guard:{typing_key}",
        )

    def resume_typing(self, typing_key: str) -> None:
        """Resume flush after typing-stop. Duplicate stops do not reset."""
        if typing_key not in self._typing:
            return
        self._typing.pop(typing_key, None)
        task = self._typing_tasks.pop(typing_key, None)
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
        for window in self._windows.values():
            if window.typing_key == typing_key:
                window.typing_paused = False
                self._arm_flush(window)

    async def _resume_typing_after_guard(self, typing_key: str) -> None:
        try:
            await asyncio.sleep(self.max_typing_wait)
        except asyncio.CancelledError:
            raise
        self.resume_typing(typing_key)

    def discard_all(self, reason: str) -> None:
        """Drop every window without flushing."""
        logger.info("Discarding all turn windows: %s", reason)
        for key in list(self._windows):
            window = self._windows.pop(key)
            self._cancel_window_task(window)
            for fragment in window.fragments:
                fragment.cleanup_temporary_local_files()
        for task in self._typing_tasks.values():
            if not task.done():
                task.cancel()
        self._typing_tasks.clear()
        self._typing.clear()

    async def terminate(self) -> None:
        """Cancel timers and drop buffers."""
        self.discard_all("terminate")
        await cancel_tracked_tasks(self._tasks)

    def _arm_flush(self, window: TurnWindow) -> None:
        if window.typing_paused:
            return
        self._cancel_window_task(window)
        remaining = window.max_total_seconds - (self._loop.time() - window.opened_at)
        delay = min(max(window.wait_seconds, 0.0), max(remaining, 0.0))
        window.flush_task = create_tracked_task(
            self._tasks,
            self._flush_after(window.key, delay),
            name=f"turn-flush:{window.key}",
        )

    async def _flush_after(self, key: str, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        window = self._windows.pop(key, None)
        if window is None or not window.fragments:
            return
        flush_event = self._build_flush_event(window)
        if not self._enqueue(flush_event):
            logger.warning("Failed to enqueue turn flush for %s", key)
            for fragment in window.fragments:
                fragment.cleanup_temporary_local_files()

    def _build_flush_event(self, window: TurnWindow) -> AstrMessageEvent:
        last = window.fragments[-1]
        texts = [
            fragment.message_str
            for fragment in window.fragments
            if fragment.message_str
        ]
        message_obj = copy.copy(last.message_obj)
        chains: list = []
        for fragment in window.fragments:
            chains.extend(list(fragment.get_messages()))
        message_obj.message = chains
        message_obj.message_id = getattr(last.message_obj, "message_id", "")
        flush = copy.copy(last)
        flush.message_str = "\n".join(texts)
        flush.message_obj = message_obj
        flush._extras = {}
        flush._result = None
        flush._force_stopped = False
        flush._has_send_oper = False
        flush.call_llm = False
        flush._temporary_local_files = []
        flush._background_tasks = set()
        flush.unified_msg_origin = last.unified_msg_origin
        flush.session_id = last.session_id
        flush.platform_member_role = last.platform_member_role
        flush.platform_role_source = getattr(last, "platform_role_source", "none")
        if (
            last.subject is not None
            and last.resource is not None
            and last.auth_context is not None
        ):
            flush.attach_authorization(
                subject=last.subject,
                resource=last.resource,
                context=last.auth_context,
            )
        for fragment in window.fragments:
            for path in list(getattr(fragment, "_temporary_local_files", [])):
                if fragment.transfer_temporary_local_file(path):
                    flush.track_temporary_local_file(path)
        flush.set_extra("should_run_command", False)
        flush.set_extra("should_run_llm", True)
        flush.set_extra("route_kind", "turn_flush")
        flush.set_extra("turn_flush", True)
        flush.set_extra("turn_continuation", True)
        flush.set_extra(MANAGER_FLUSH_TOKEN, MANAGER_FLUSH_SENTINEL)
        flush.set_extra("wake_reasons", {"turn_continuation"})
        flush.is_wake = True
        flush.is_at_or_wake_command = True
        return flush

    def _cancel_window_task(self, window: TurnWindow) -> None:
        task = window.flush_task
        window.flush_task = None
        if task is not None and not task.done():
            task.cancel()

    def _evict_oldest_window(self) -> None:
        while len(self._windows) >= self._max_windows:
            key, window = self._windows.popitem(last=False)
            self._cancel_window_task(window)
            logger.warning("Evicted oldest turn window %s", key)
            for fragment in window.fragments:
                fragment.cleanup_temporary_local_files()

    def _evict_oldest_typing(self) -> None:
        while len(self._typing) >= self._max_typing:
            key, _ = self._typing.popitem(last=False)
            task = self._typing_tasks.pop(key, None)
            if task is not None and not task.done():
                task.cancel()
            for window in self._windows.values():
                if window.typing_key == key:
                    window.typing_paused = False
                    self._arm_flush(window)
