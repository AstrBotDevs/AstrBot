"""Session-based conversational flow management.

本模块实现会话等待器 (session_waiter)，用于构建多轮对话流程。

核心组件：
- SessionController: 控制会话生命周期，支持超时管理、会话保持、历史记录
- SessionWaiterManager: 管理活跃的会话等待器，处理事件分发和注册/注销
- @session_waiter 装饰器: 将普通 handler 转换为会话式 handler

使用场景：
当需要在用户首次触发后继续监听后续消息（如分步表单、问答游戏），
可使用 @session_waiter 装饰器自动管理会话状态和超时。

注意事项：
在当前桥接设计中，不应在普通 SDK handler 内直接 await session_waiter，
这会导致首次 dispatch 保持打开直到下一条消息到达。
推荐写法是 `await ctx.register_task(waiter(...), "...")`，让 waiter 在后台任务中
承接后续消息；直接 await 仅适用于你明确需要保持当前 dispatch 挂起的场景。
"""

from __future__ import annotations

import asyncio
import time
import weakref
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from functools import wraps
from contextvars import ContextVar
from typing import Any, Concatenate, ParamSpec, Protocol, TypeVar, cast, overload

from loguru import logger

from ._internal.invocation_context import current_caller_plugin_id
from .events import MessageEvent

_OwnerT = TypeVar("_OwnerT")
_P = ParamSpec("_P")
_ResultT = TypeVar("_ResultT")
_WaiterKey = tuple[str, str]

_HANDLER_TASKS: weakref.WeakSet[asyncio.Task[Any]] = weakref.WeakSet()
_REGISTERED_BACKGROUND_TASKS: weakref.WeakSet[asyncio.Task[Any]] = weakref.WeakSet()
_WARNED_DIRECT_WAIT_TASKS: weakref.WeakSet[asyncio.Task[Any]] = weakref.WeakSet()
_ACTIVE_WAITER_KEY: ContextVar[_WaiterKey | None] = ContextVar(
    "astrbot_sdk_active_waiter_key",
    default=None,
)


def _mark_session_waiter_handler_task(task: asyncio.Task[Any]) -> None:
    _HANDLER_TASKS.add(task)


def _unmark_session_waiter_handler_task(task: asyncio.Task[Any]) -> None:
    _HANDLER_TASKS.discard(task)


def _mark_session_waiter_background_task(task: asyncio.Task[Any]) -> None:
    _REGISTERED_BACKGROUND_TASKS.add(task)


def _unmark_session_waiter_background_task(task: asyncio.Task[Any]) -> None:
    _REGISTERED_BACKGROUND_TASKS.discard(task)


class _SessionWaiterDecorator(Protocol):
    @overload
    def __call__(
        self,
        func: Callable[
            Concatenate[SessionController, MessageEvent, _P],
            Awaitable[_ResultT],
        ],
        /,
    ) -> Callable[Concatenate[MessageEvent, _P], Coroutine[Any, Any, _ResultT]]: ...

    @overload
    def __call__(
        self,
        func: Callable[
            Concatenate[_OwnerT, SessionController, MessageEvent, _P],
            Awaitable[_ResultT],
        ],
        /,
    ) -> Callable[
        Concatenate[_OwnerT, MessageEvent, _P],
        Coroutine[Any, Any, _ResultT],
    ]: ...


@dataclass(slots=True)
class SessionController:
    future: asyncio.Future[Any] = field(default_factory=asyncio.Future)
    current_event: asyncio.Event | None = None
    ts: float | None = None
    timeout: float | None = None
    history_chains: list[list[dict[str, Any]]] = field(default_factory=list)

    def stop(self, error: Exception | None = None) -> None:
        if self.future.done():
            return
        if error is not None:
            self.future.set_exception(error)
        else:
            self.future.set_result(None)

    def keep(self, timeout: float = 0, reset_timeout: bool = False) -> None:
        new_ts = time.time()
        if reset_timeout:
            if timeout <= 0:
                self.stop()
                return
        else:
            assert self.timeout is not None
            assert self.ts is not None
            left_timeout = self.timeout - (new_ts - self.ts)
            timeout = left_timeout + timeout
            if timeout <= 0:
                self.stop()
                return

        if self.current_event and not self.current_event.is_set():
            self.current_event.set()

        current_event = asyncio.Event()
        self.current_event = current_event
        self.ts = new_ts
        self.timeout = timeout
        asyncio.create_task(self._holding(current_event, timeout))

    async def _holding(self, event: asyncio.Event, timeout: float) -> None:
        try:
            await asyncio.wait_for(event.wait(), timeout)
        except asyncio.TimeoutError as exc:
            self.stop(exc)
        except asyncio.CancelledError:
            return

    def get_history_chains(self) -> list[list[dict[str, Any]]]:
        return list(self.history_chains)


@dataclass(slots=True)
class _WaiterEntry:
    session_key: str
    plugin_id: str
    handler: Callable[[SessionController, MessageEvent], Awaitable[Any]]
    controller: SessionController
    record_history_chains: bool
    unregister_enabled: bool = True


class SessionWaiterManager:
    def __init__(self, *, plugin_id: str, peer) -> None:
        self._plugin_id = plugin_id
        self._peer = peer
        self._entries: dict[str, dict[str, _WaiterEntry]] = {}
        self._locks: dict[_WaiterKey, asyncio.Lock] = {}

    @staticmethod
    def _make_key(*, plugin_id: str, session_key: str) -> _WaiterKey:
        return (plugin_id, session_key)

    async def register(
        self,
        *,
        event: MessageEvent,
        handler: Callable[[SessionController, MessageEvent], Awaitable[Any]],
        timeout: int,
        record_history_chains: bool,
    ) -> Any:
        if event._context is None:
            raise RuntimeError("session_waiter requires runtime context")
        self._warn_if_direct_wait_in_handler(event)
        session_key = event.unified_msg_origin
        plugin_id = self._resolve_plugin_id(event)
        entry = _WaiterEntry(
            session_key=session_key,
            plugin_id=plugin_id,
            handler=handler,
            controller=SessionController(),
            record_history_chains=record_history_chains,
        )
        previous = self._entries.setdefault(session_key, {}).get(plugin_id)
        restorable_previous: _WaiterEntry | None = None
        self._entries[session_key][plugin_id] = entry
        self._lock_for(session_key, plugin_id)
        if previous is not None:
            previous.unregister_enabled = False
            if _ACTIVE_WAITER_KEY.get() == self._make_key(
                plugin_id=plugin_id,
                session_key=session_key,
            ):
                restorable_previous = previous
            else:
                self._finish_entry(
                    previous,
                    RuntimeError("session waiter replaced by a newer waiter"),
                )
            logger.warning(
                "Session waiter replaced: plugin_id={} session_key={}",
                plugin_id,
                session_key,
            )
        try:
            await self._invoke_system_waiter(
                "system.session_waiter.register",
                session_key=session_key,
                plugin_id=plugin_id,
            )
            entry.controller.keep(timeout, reset_timeout=True)
        except Exception:
            entry.unregister_enabled = False
            await self._remove_entry(entry)
            if restorable_previous is not None:
                self._entries.setdefault(session_key, {})[plugin_id] = (
                    restorable_previous
                )
                restorable_previous.unregister_enabled = True
                self._lock_for(session_key, plugin_id)
            raise
        try:
            return await entry.controller.future
        finally:
            if entry.unregister_enabled:
                await self.unregister(session_key, plugin_id=plugin_id)

    def _warn_if_direct_wait_in_handler(self, event: MessageEvent) -> None:
        current_task = asyncio.current_task()
        if current_task is None:
            return
        if current_task not in _HANDLER_TASKS:
            return
        if current_task in _REGISTERED_BACKGROUND_TASKS:
            return
        if current_task in _WARNED_DIRECT_WAIT_TASKS:
            return
        _WARNED_DIRECT_WAIT_TASKS.add(current_task)
        logger.warning(
            "Direct await on session_waiter blocks the current handler dispatch; "
            'prefer `await ctx.register_task(waiter(...), "...")`: '
            "plugin_id={} session_key={}",
            event._context.plugin_id,
            event.unified_msg_origin,
        )

    async def wait_for_event(
        self,
        *,
        event: MessageEvent,
        timeout: int,
        record_history_chains: bool = False,
    ) -> MessageEvent:
        future: asyncio.Future[MessageEvent] = (
            asyncio.get_running_loop().create_future()
        )

        async def _handler(
            controller: SessionController,
            waiter_event: MessageEvent,
        ) -> None:
            if not future.done():
                future.set_result(waiter_event)
            controller.stop()

        await self.register(
            event=event,
            handler=_handler,
            timeout=timeout,
            record_history_chains=record_history_chains,
        )
        return future.result()

    async def unregister(
        self,
        session_key: str,
        *,
        plugin_id: str | None = None,
    ) -> None:
        target_plugin_id = self._resolve_unregister_plugin_id(
            session_key,
            plugin_id=plugin_id,
        )
        if target_plugin_id is None:
            return
        lock_key = (session_key, target_plugin_id)
        lock = self._lock_for(session_key, target_plugin_id)
        removed = False
        async with lock:
            session_entries = self._entries.get(session_key)
            if session_entries is None:
                return
            removed = session_entries.pop(target_plugin_id, None) is not None
            if not session_entries:
                self._entries.pop(session_key, None)
        if self._locks.get(lock_key) is lock:
            self._locks.pop(lock_key, None)
        if not removed:
            return
        try:
            await self._invoke_system_waiter(
                "system.session_waiter.unregister",
                session_key=session_key,
                plugin_id=target_plugin_id,
            )
        except Exception:
            logger.debug(
                "Failed to unregister session waiter: plugin_id={} session_key={}",
                target_plugin_id,
                session_key,
            )

    async def fail(
        self,
        session_key: str,
        error: Exception,
        *,
        plugin_id: str | None = None,
    ) -> bool:
        resolved_plugin_id = plugin_id
        if resolved_plugin_id is None:
            caller_plugin_id = current_caller_plugin_id()
            if caller_plugin_id:
                resolved_plugin_id = caller_plugin_id
        entry = self._select_entry(
            session_key,
            plugin_id=resolved_plugin_id,
            allow_ambiguous=False,
            missing_result=None,
        )
        if entry is None:
            return False
        lock = self._lock_for(session_key, entry.plugin_id)
        async with lock:
            current = self._get_entry(session_key, entry.plugin_id)
            if current is None or current.controller.future.done():
                return False
            self._finish_entry(current, error)
            return True

    def has_active_waiter(self, event: MessageEvent) -> bool:
        session_key = event.unified_msg_origin
        event_plugin_id = self._event_plugin_id(event)
        if event_plugin_id is not None:
            entry = self._get_entry(session_key, event_plugin_id)
            return entry is not None and not entry.controller.future.done()
        return bool(self.get_waiter_plugin_ids(session_key))

    def has_waiter(self, event: MessageEvent) -> bool:
        return self.has_active_waiter(event)

    def get_waiter_plugin_ids(self, session_key: str) -> list[str]:
        return sorted(
            plugin_id
            for plugin_id, entry in self._entries.get(session_key, {}).items()
            if not entry.controller.future.done()
        )

    async def dispatch(
        self,
        event: MessageEvent,
        *,
        plugin_id: str | None = None,
    ) -> dict[str, Any]:
        if event._context is None:
            raise RuntimeError("session_waiter dispatch requires runtime context")
        session_key = event.unified_msg_origin
        entry = self._select_entry(
            session_key,
            plugin_id=plugin_id,
            allow_ambiguous=False,
            missing_result=None,
            ambiguous_error=LookupError(
                f"session waiter dispatch for session '{session_key}' requires explicit plugin identity"
            ),
        )
        if entry is None:
            return {"sent_message": False, "stop": False, "call_llm": False}
        lock = self._lock_for(session_key, entry.plugin_id)
        async with lock:
            current = self._get_entry(session_key, entry.plugin_id)
            if current is None or current.controller.future.done():
                return {"sent_message": False, "stop": False, "call_llm": False}
            waiter_event = self._build_waiter_event(current, event)
            if current.record_history_chains:
                chain = []
                raw_chain = (
                    waiter_event.raw.get("chain")
                    if isinstance(waiter_event.raw, dict)
                    else None
                )
                if isinstance(raw_chain, list):
                    chain = [dict(item) for item in raw_chain if isinstance(item, dict)]
                current.controller.history_chains.append(chain)
        active_key_token = _ACTIVE_WAITER_KEY.set(
            self._make_key(
                plugin_id=current.plugin_id,
                session_key=current.session_key,
            )
        )
        try:
            await current.handler(current.controller, waiter_event)
        finally:
            _ACTIVE_WAITER_KEY.reset(active_key_token)
        return {
            "sent_message": False,
            "stop": waiter_event.is_stopped(),
            "call_llm": False,
        }

    def _resolve_plugin_id(self, event: MessageEvent) -> str:
        caller_plugin_id = current_caller_plugin_id()
        if caller_plugin_id:
            return caller_plugin_id
        context = event._context
        if context is not None and context.plugin_id.strip():
            return context.plugin_id
        return self._plugin_id

    @staticmethod
    def _event_plugin_id(event: MessageEvent) -> str | None:
        context = event._context
        if context is None:
            return None
        plugin_id = context.plugin_id.strip()
        return plugin_id or None

    def _resolve_unregister_plugin_id(
        self,
        session_key: str,
        *,
        plugin_id: str | None,
    ) -> str | None:
        if plugin_id is not None:
            normalized = str(plugin_id).strip()
            return normalized or None
        session_entries = self._entries.get(session_key, {})
        if len(session_entries) != 1:
            return None
        return next(iter(session_entries))

    def _select_entry(
        self,
        session_key: str,
        *,
        plugin_id: str | None,
        allow_ambiguous: bool,
        missing_result: _WaiterEntry | None,
        ambiguous_error: Exception | None = None,
    ) -> _WaiterEntry | None:
        if plugin_id is not None:
            return self._get_entry(session_key, plugin_id)
        active_entries = [
            entry
            for entry in self._entries.get(session_key, {}).values()
            if not entry.controller.future.done()
        ]
        if not active_entries:
            return missing_result
        if len(active_entries) > 1 and not allow_ambiguous:
            if ambiguous_error is not None:
                raise ambiguous_error
            return missing_result
        return active_entries[0]

    def _get_entry(self, session_key: str, plugin_id: str) -> _WaiterEntry | None:
        return self._entries.get(session_key, {}).get(plugin_id)

    def _lock_for(self, session_key: str, plugin_id: str) -> asyncio.Lock:
        return self._locks.setdefault((session_key, plugin_id), asyncio.Lock())

    async def _remove_entry(self, entry: _WaiterEntry) -> None:
        lock_key = (entry.session_key, entry.plugin_id)
        lock = self._lock_for(entry.session_key, entry.plugin_id)
        async with lock:
            session_entries = self._entries.get(entry.session_key)
            if session_entries is None:
                return
            current = session_entries.get(entry.plugin_id)
            if current is not entry:
                return
            session_entries.pop(entry.plugin_id, None)
            if not session_entries:
                self._entries.pop(entry.session_key, None)
        if self._locks.get(lock_key) is lock:
            self._locks.pop(lock_key, None)

    @staticmethod
    def _finish_entry(entry: _WaiterEntry, error: Exception | None = None) -> None:
        entry.controller.stop(error)
        if (
            entry.controller.current_event is not None
            and not entry.controller.current_event.is_set()
        ):
            entry.controller.current_event.set()

    async def _invoke_system_waiter(
        self,
        capability: str,
        *,
        session_key: str,
        plugin_id: str,
    ) -> None:
        from ._internal.invocation_context import caller_plugin_scope

        with caller_plugin_scope(plugin_id):
            await self._peer.invoke(
                capability,
                {"session_key": session_key},
            )

    def _build_waiter_event(
        self,
        entry: _WaiterEntry,
        event: MessageEvent,
    ) -> MessageEvent:
        from .context import Context

        source_payload = self._source_payload_from_event(event)
        cancel_token = (
            event._context.cancel_token if event._context is not None else None
        )
        waiter_context = Context(
            peer=self._peer,
            plugin_id=entry.plugin_id,
            request_id=(
                event._context.request_id if event._context is not None else None
            ),
            cancel_token=cancel_token,
            source_event_payload=source_payload,
        )
        # Rebuild the event so the waiter always sees the registering plugin identity
        # and the exact source payload that triggered the follow-up dispatch.
        return MessageEvent.from_payload(
            source_payload,
            context=waiter_context,
        )

    @staticmethod
    def _source_payload_from_event(event: MessageEvent) -> dict[str, Any]:
        raw_payload = event.raw if isinstance(event.raw, dict) else None
        if raw_payload is not None and {
            "text",
            "session_id",
            "platform",
        }.issubset(raw_payload):
            return dict(raw_payload)
        return event.to_payload()


def session_waiter(
    timeout: int = 30,
    *,
    record_history_chains: bool = False,
) -> _SessionWaiterDecorator:
    def decorator(
        func: Callable[..., Awaitable[Any]],
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            owner = None
            event: MessageEvent | None = None
            trailing_args: tuple[Any, ...] = ()
            if args and isinstance(args[0], MessageEvent):
                event = args[0]
                trailing_args = args[1:]
            elif len(args) >= 2 and isinstance(args[1], MessageEvent):
                owner = args[0]
                event = args[1]
                trailing_args = args[2:]
            if event is None:
                raise RuntimeError("session_waiter requires a MessageEvent argument")
            if event._context is None:
                raise RuntimeError("session_waiter requires runtime context")
            manager = getattr(event._context.peer, "_session_waiter_manager", None)
            if manager is None:
                raise RuntimeError("session_waiter manager is unavailable")

            if owner is None:
                free_func = cast(Callable[..., Awaitable[Any]], func)

                async def bound_handler(
                    controller: SessionController,
                    waiter_event: MessageEvent,
                ) -> Any:
                    return await free_func(
                        controller,
                        waiter_event,
                        *trailing_args,
                        **kwargs,
                    )
            else:
                method_func = cast(Callable[..., Awaitable[Any]], func)

                async def bound_handler(
                    controller: SessionController,
                    waiter_event: MessageEvent,
                ) -> Any:
                    return await method_func(
                        owner,
                        controller,
                        waiter_event,
                        *trailing_args,
                        **kwargs,
                    )

            return await manager.register(
                event=event,
                handler=bound_handler,
                timeout=timeout,
                record_history_chains=record_history_chains,
            )

        return wrapper

    return cast(_SessionWaiterDecorator, decorator)


__all__ = [
    "_OwnerT",
    "_P",
    "_ResultT",
    "SessionController",
    "SessionWaiterManager",
    "session_waiter",
]
