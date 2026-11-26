"""Legacy session_waiter compatibility built on the message.wait capability.

Old plugins register multi-turn waits with @session_waiter and a
SessionController; in the isolated Runner the same semantics are replicated
on top of ctx.sessions.wait: the Host claims matching inbound events and
pushes them here, while this module drives the legacy handler and its
keep/stop clock locally.
"""

from __future__ import annotations

import abc
import asyncio
import contextlib
import copy
import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any

from ...services.sessions import SessionFilter as SDKSessionFilter
from .event import AstrMessageEvent
from .platform_events import build_legacy_event
from .star import StarTools

USER_SESSIONS: dict[str, SessionWaiter] = {}  # 存储 SessionWaiter 实例
FILTERS: list[SessionFilter] = []  # 存储 SessionFilter 实例


class SessionController:
    """控制一个 Session 是否已经结束"""

    def __init__(self) -> None:
        self.future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self.current_event: asyncio.Event | None = None
        """当前正在等待的所用的异步事件"""
        self.ts: float | None = None
        """上次保持(keep)开始时的时间"""
        self.timeout: float | int | None = None
        """上次保持(keep)开始时的超时时间"""

        self.history_chains: list[list[Any]] = []

    def stop(self, error: Exception | None = None) -> None:
        """立即结束这个会话"""
        if not self.future.done():
            if error:
                self.future.set_exception(error)
            else:
                self.future.set_result(None)

    def keep(self, timeout: float = 0, reset_timeout: bool = False) -> None:
        """保持这个会话

        Args:
            timeout (float): 必填。会话超时时间。
            当 reset_timeout 设置为 True 时, 代表重置超时时间,
            timeout 必须 > 0, 如果 <= 0 则立即结束会话。
            当 reset_timeout 设置为 False 时, 代表继续维持原来的超时时间,
            新 timeout = 原来剩余的timeout + timeout (可以 < 0)

        """
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
            self.current_event.set()  # 通知上一个 keep 结束

        new_event = asyncio.Event()
        self.ts = new_ts
        self.current_event = new_event
        self.timeout = timeout

    def _remaining(self) -> float:
        """Return the time left on the current keep clock in seconds."""
        if self.ts is None or self.timeout is None:
            return 0.0
        return self.timeout - (time.time() - self.ts)

    def get_history_chains(self) -> list[list[Any]]:
        """获取历史消息链"""
        return self.history_chains


class SessionFilter:
    """如何界定一个会话"""

    @abc.abstractmethod
    def filter(self, event: AstrMessageEvent) -> str:
        """根据事件返回一个会话标识符"""


class DefaultSessionFilter(SessionFilter):
    def filter(self, event: AstrMessageEvent) -> str:
        """默认实现，返回统一消息来源字符串作为会话标识符"""
        return event.unified_msg_origin


class _LegacyFilterAdapter(SDKSessionFilter):
    """Adapt one legacy SessionFilter onto the SDK session machinery."""

    def __init__(
        self,
        legacy_filter: SessionFilter,
        context: Any,
        *,
        umo_scoped: bool,
    ) -> None:
        """Initialize the adapter.

        Args:
            legacy_filter: Legacy filter receiving facade events.
            context: Compat Context used to build facade events.
            umo_scoped: Whether the filter only matches the initiating UMO.
        """
        self._legacy_filter = legacy_filter
        self._context = context
        self.umo_scoped = umo_scoped

    def filter(self, event: Any) -> str:
        """Return the legacy session key for one SDK event."""
        return self._legacy_filter.filter(build_legacy_event(event, self._context))


class SessionWaiter:
    def __init__(
        self,
        session_filter: SessionFilter,
        session_id: str,
        record_history_chains: bool,
        *,
        event: Any = None,
        context: Any = None,
    ) -> None:
        self.session_id = session_id
        self.session_filter = session_filter
        self.handler: (
            Callable[[SessionController, AstrMessageEvent], Awaitable[Any]] | None
        ) = None  # 处理函数

        self.session_controller = SessionController()
        self.record_history_chains = record_history_chains
        """是否记录历史消息链"""

        self._sdk_event = event
        self._context = context

    async def register_wait(
        self,
        handler: Callable[[SessionController, AstrMessageEvent], Awaitable[Any]],
        timeout: int = 30,  # noqa: ASYNC109
    ) -> Any:
        """等待外部输入并处理"""
        self.handler = handler
        USER_SESSIONS[self.session_id] = self

        context = StarTools._bound() if self._context is None else self._context
        sdk_ctx = context._inner
        adapter = _LegacyFilterAdapter(
            self.session_filter,
            context,
            umo_scoped=isinstance(self.session_filter, DefaultSessionFilter),
        )

        # 开始一个会话保持事件
        self.session_controller.keep(timeout, reset_timeout=True)

        try:
            async with sdk_ctx.sessions.wait(
                self._sdk_event,
                filter=adapter,
                timeout=timeout,
            ) as session:
                driver = asyncio.create_task(self._drive(session, context))
                try:
                    return await self.session_controller.future
                finally:
                    driver.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await driver
        finally:
            # Clean up once on success, failure, or cancellation. A shared filter
            # can have another registration that must not be removed twice.
            self._cleanup()

    async def _drive(self, session: Any, context: Any) -> None:
        """Feed matched events into the legacy handler until the session ends.

        The legacy clock keeps ticking while the handler runs: each turn
        re-arms the Host deadline with the time left on the current keep.
        """
        controller = self.session_controller
        try:
            while not controller.future.done():
                remaining = controller._remaining()
                if remaining <= 0:
                    controller.stop(TimeoutError("等待超时"))
                    return
                try:
                    sdk_event = await session.next(timeout=remaining)
                except TimeoutError:
                    controller.stop(TimeoutError("等待超时"))
                    return
                facade = build_legacy_event(sdk_event, context)
                if self.record_history_chains:
                    controller.history_chains.append(
                        [copy.deepcopy(comp) for comp in facade.get_messages()],
                    )
                try:
                    assert self.handler is not None
                    await self.handler(controller, facade)
                except Exception as exc:
                    controller.stop(exc)
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            controller.stop(exc)

    def _cleanup(self, error: Exception | None = None) -> None:
        """清理会话"""
        USER_SESSIONS.pop(self.session_id, None)
        try:
            FILTERS.remove(self.session_filter)
        except ValueError:
            pass
        self.session_controller.stop(error)

    @classmethod
    async def trigger(cls, session_id: str, event: AstrMessageEvent) -> None:
        """外部输入触发会话处理

        In isolated mode inbound delivery is Host-driven through the
        message.wait capability; this stays as a no-op for API parity.
        """


def session_waiter(timeout: int = 30, record_history_chains: bool = False):
    """装饰器：自动将函数注册为 SessionWaiter 处理函数，并等待外部输入触发执行。

    :param timeout: 超时时间（秒）
    :param record_history_chain: 是否自动记录历史消息链。
    可以通过 controller.get_history_chains() 获取。深拷贝。
    """

    def decorator(
        func: Callable[[SessionController, AstrMessageEvent], Awaitable[Any]],
    ):
        @functools.wraps(func)
        async def wrapper(
            event: AstrMessageEvent,
            session_filter: SessionFilter | None = None,
            *args,
            **kwargs,
        ):
            if not session_filter:
                session_filter = DefaultSessionFilter()
            if not isinstance(session_filter, SessionFilter):
                raise ValueError("session_filter 必须是 SessionFilter")

            context = StarTools._bound()
            session_id = session_filter.filter(event)
            FILTERS.append(session_filter)

            waiter = SessionWaiter(
                session_filter,
                session_id,
                record_history_chains,
                event=event._event,
                context=context,
            )
            return await waiter.register_wait(func, timeout)

        return wrapper

    return decorator
