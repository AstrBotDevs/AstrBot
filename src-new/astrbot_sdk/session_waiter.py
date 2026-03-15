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
如需非阻塞的会话等待，应从后台任务启动或添加显式的调度/恢复机制。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from .events import MessageEvent


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
    handler: Callable[[SessionController, MessageEvent], Awaitable[Any]]
    controller: SessionController
    record_history_chains: bool


class SessionWaiterManager:
    def __init__(self, *, plugin_id: str, peer) -> None:
        self._plugin_id = plugin_id
        self._peer = peer
        self._entries: dict[str, _WaiterEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

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
        session_key = event.unified_msg_origin
        entry = _WaiterEntry(
            session_key=session_key,
            handler=handler,
            controller=SessionController(),
            record_history_chains=record_history_chains,
        )
        replaced = session_key in self._entries
        self._entries[session_key] = entry
        self._locks.setdefault(session_key, asyncio.Lock())
        if replaced:
            logger.warning(
                "Session waiter replaced: plugin_id=%s session_key=%s",
                self._plugin_id,
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
            await self.unregister(session_key)

    async def unregister(self, session_key: str) -> None:
        self._entries.pop(session_key, None)
        self._locks.pop(session_key, None)
        try:
            await self._peer.invoke(
                "system.session_waiter.unregister",
                {"session_key": session_key},
            )
        except Exception:
            logger.debug(
                "Failed to unregister session waiter: plugin_id=%s session_key=%s",
                self._plugin_id,
                session_key,
            )

    def has_waiter(self, event: MessageEvent) -> bool:
        return event.unified_msg_origin in self._entries

    async def dispatch(self, event: MessageEvent) -> dict[str, Any]:
        session_key = event.unified_msg_origin
        entry = self._entries.get(session_key)
        if entry is None:
            return {"sent_message": False, "stop": False, "call_llm": False}
        lock = self._locks.setdefault(session_key, asyncio.Lock())
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
):
    def decorator(
        func: Callable[[SessionController, MessageEvent], Awaitable[Any]],
    ):
        async def wrapper(*args, **kwargs):
            owner = None
            event: MessageEvent | None = None
            trailing_args = ()
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

                async def bound_handler(
                    controller: SessionController,
                    waiter_event: MessageEvent,
                ) -> Any:
                    return await func(
                        controller,
                        waiter_event,
                        *trailing_args,
                        **kwargs,
                    )
            else:

                async def bound_handler(
                    controller: SessionController,
                    waiter_event: MessageEvent,
                ) -> Any:
                    return await func(
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

    return decorator
