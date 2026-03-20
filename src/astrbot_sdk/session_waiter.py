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
from typing import Any, Concatenate, ParamSpec, Protocol, TypeVar, cast, overload

from loguru import logger

from .events import MessageEvent

_OwnerT = TypeVar("_OwnerT")
_P = ParamSpec("_P")
_ResultT = TypeVar("_ResultT")
_WaiterKey = tuple[str, str]

_HANDLER_TASKS: weakref.WeakSet[asyncio.Task[Any]] = weakref.WeakSet()
_REGISTERED_BACKGROUND_TASKS: weakref.WeakSet[asyncio.Task[Any]] = weakref.WeakSet()
_WARNED_DIRECT_WAIT_TASKS: weakref.WeakSet[asyncio.Task[Any]] = weakref.WeakSet()


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


class SessionWaiterManager:
    def __init__(self, *, plugin_id: str, peer) -> None:
        self._plugin_id = plugin_id
        self._peer = peer
        self._entries: dict[_WaiterKey, _WaiterEntry] = {}
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
        plugin_id = event._context.plugin_id
        self._warn_if_direct_wait_in_handler(event)
        session_key = event.unified_msg_origin
        key = self._make_key(plugin_id=plugin_id, session_key=session_key)
        entry = _WaiterEntry(
            session_key=session_key,
            plugin_id=plugin_id,
            handler=handler,
            controller=SessionController(),
            record_history_chains=record_history_chains,
        )
        replaced = key in self._entries
        self._entries[key] = entry
        self._locks.setdefault(key, asyncio.Lock())
        if replaced:
            logger.warning(
                "Session waiter replaced: plugin_id=%s session_key=%s",
                plugin_id,
                session_key,
            )
        await self._peer.invoke(
            "system.session_waiter.register",
            {"session_key": session_key},
        )
        entry.controller.keep(timeout, reset_timeout=True)
        try:
            return await entry.controller.future
        finally:
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
            self._plugin_id,
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
        self, session_key: str, *, plugin_id: str | None = None
    ) -> None:
        if plugin_id is None:
            plugin_ids = self.get_waiter_plugin_ids(session_key)
            if len(plugin_ids) != 1:
                return
            plugin_id = plugin_ids[0]

        key = self._make_key(plugin_id=plugin_id, session_key=session_key)
        self._entries.pop(key, None)
        self._locks.pop(key, None)
        try:
            await self._peer.invoke(
                "system.session_waiter.unregister",
                {"session_key": session_key},
            )
        except Exception:
            logger.debug(
                "Failed to unregister session waiter: plugin_id=%s session_key=%s",
                plugin_id,
                session_key,
            )

    async def fail(
        self,
        session_key: str,
        error: Exception,
        *,
        plugin_id: str | None = None,
    ) -> bool:
        if plugin_id is None:
            plugin_ids = self.get_waiter_plugin_ids(session_key)
            if len(plugin_ids) != 1:
                return False
            plugin_id = plugin_ids[0]

        key = self._make_key(plugin_id=plugin_id, session_key=session_key)
        entry = self._entries.get(key)
        if entry is None:
            return False
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            current = self._entries.get(key)
            if current is None:
                return False
            current.controller.stop(error)
            if (
                current.controller.current_event is not None
                and not current.controller.current_event.is_set()
            ):
                current.controller.current_event.set()
            return True

    def has_active_waiter(self, event: MessageEvent) -> bool:
        session_key = event.unified_msg_origin
        return any(
            entry.session_key == session_key and not entry.controller.future.done()
            for entry in self._entries.values()
        )

    def has_waiter(self, event: MessageEvent) -> bool:
        return self.has_active_waiter(event)

    def get_waiter_plugin_ids(self, session_key: str) -> list[str]:
        return [
            entry.plugin_id
            for entry in self._entries.values()
            if entry.session_key == session_key and not entry.controller.future.done()
        ]

    async def dispatch(
        self, event: MessageEvent, *, plugin_id: str | None = None
    ) -> dict[str, Any]:
        if event._context is None:
            raise RuntimeError("session_waiter dispatch requires runtime context")
        current_plugin_id = plugin_id or event._context.plugin_id
        session_key = event.unified_msg_origin
        key = self._make_key(plugin_id=current_plugin_id, session_key=session_key)
        entry = self._entries.get(key)
        if entry is None:
            return {"sent_message": False, "stop": False, "call_llm": False}
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if entry.record_history_chains:
                chain = []
                raw_chain = (
                    event.raw.get("chain") if isinstance(event.raw, dict) else None
                )
                if isinstance(raw_chain, list):
                    chain = [dict(item) for item in raw_chain if isinstance(item, dict)]
                entry.controller.history_chains.append(chain)
            await entry.handler(entry.controller, event)
            return {
                "sent_message": False,
                "stop": event.is_stopped(),
                "call_llm": False,
            }


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
