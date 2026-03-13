"""旧版 ``session_waiter`` 的最小兼容实现。"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any


@dataclass
class _SessionWaitState:
    queue: asyncio.Queue[Any]
    timeout: float | None
    stopped: bool = False


class SessionController:
    """兼容旧版交互式会话等待控制器。"""

    def __init__(self, state: _SessionWaitState) -> None:
        self._state = state

    def keep(
        self,
        *,
        timeout: float | None = None,
        reset_timeout: bool = False,
    ) -> None:
        if timeout is not None and (reset_timeout or self._state.timeout is None):
            self._state.timeout = timeout
        self._state.stopped = False

    def stop(self) -> None:
        self._state.stopped = True


class SessionWaiterManager:
    """按会话路由后续消息到等待中的 compat 回调。"""

    def __init__(self) -> None:
        self._waiters: dict[str, _SessionWaitState] = {}

    @staticmethod
    def session_key(event: Any) -> str:
        event = SessionWaiterManager._coerce_event(event)
        unified = getattr(event, "unified_msg_origin", None)
        if unified:
            return str(unified)
        session = getattr(event, "session_id", "")
        return str(session)

    def register(self, event: Any, state: _SessionWaitState) -> str:
        key = self.session_key(event)
        if key in self._waiters:
            raise RuntimeError(f"session_waiter 已存在活跃会话: {key}")
        self._waiters[key] = state
        return key

    def unregister(self, key: str, state: _SessionWaitState) -> None:
        if self._waiters.get(key) is state:
            self._waiters.pop(key, None)

    async def dispatch(self, event: Any) -> bool:
        key = self.session_key(event)
        state = self._waiters.get(key)
        if state is None:
            return False
        await state.queue.put(self._coerce_event(event))
        return True

    @staticmethod
    def _coerce_event(event: Any) -> Any:
        from .api.event import AstrMessageEvent

        if isinstance(event, AstrMessageEvent):
            return event
        return AstrMessageEvent.from_message_event(event)


def session_waiter(
    *,
    timeout: float | None = None,
    record_history_chains: bool | None = None,
):
    """兼容旧版 ``@session_waiter`` 装饰器。

    当前实现只保留运行时等待下一条同会话消息的核心语义；
    ``record_history_chains`` 仅为兼容旧签名而保留。
    """

    del record_history_chains

    def decorator(func):
        async def runner(event: Any, *args: Any, **kwargs: Any) -> None:
            context = getattr(event, "_context", None)
            manager = getattr(context, "_session_waiter_manager", None)
            if manager is None:
                raise RuntimeError("session_waiter 只能在插件运行时消息上下文中使用")

            state = _SessionWaitState(queue=asyncio.Queue(), timeout=timeout)
            key = manager.register(event, state)
            try:
                while True:
                    try:
                        next_event = await asyncio.wait_for(
                            state.queue.get(),
                            timeout=state.timeout,
                        )
                    except asyncio.TimeoutError as exc:
                        raise TimeoutError from exc

                    controller = SessionController(state)
                    result = func(controller, next_event, *args, **kwargs)
                    if inspect.isawaitable(result):
                        await result
                    if state.stopped:
                        return
            finally:
                manager.unregister(key, state)

        runner.__name__ = getattr(func, "__name__", "session_waiter")
        runner.__doc__ = getattr(func, "__doc__", None)
        runner.__wrapped__ = func
        return runner

    return decorator


__all__ = ["SessionController", "SessionWaiterManager", "session_waiter"]
