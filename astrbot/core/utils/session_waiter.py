"""会话控制"""

import abc
import asyncio
import copy
import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any

import astrbot.core.message.components as Comp
from astrbot.core.platform import AstrMessageEvent

USER_SESSIONS: dict[str, "SessionWaiter"] = {}  # 存储 SessionWaiter 实例
FILTERS: list["SessionFilter"] = []  # 存储 SessionFilter 实例


class SessionController:
    """控制一个 Session 是否已经结束"""

    def __init__(self) -> None:
        self.future = asyncio.Future()
        self.current_event: asyncio.Event | None = None
        """当前正在等待的所用的异步事件"""
        self.ts: float | None = None
        """上次保持(keep)开始时的时间"""
        self.timeout: float | int | None = None
        """上次保持(keep)开始时的超时时间"""

        self.history_chains: list[list[Comp.BaseMessageComponent]] = []

    def stop(self, error: Exception | None = None) -> None:
        """立即结束这个会话"""
        if not self.future.done():
            if error:
                self.future.set_exception(error)
            else:
                self.future.set_result(None)

    def keep(self, timeout: float = 0, reset_timeout=False) -> None:
        """保持这个会话

        Args:
            timeout (float): 必填。会话超时时间。
            当 reset_timeout 设置为 True 时, 代表重置超时时间, timeout 必须 > 0, 如果 <= 0 则立即结束会话。
            当 reset_timeout 设置为 False 时, 代表继续维持原来的超时时间, 新 timeout = 原来剩余的timeout + timeout (可以 < 0)

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

        asyncio.create_task(self._holding(new_event, timeout))  # 开始新的 keep

    async def _holding(self, event: asyncio.Event, timeout: float) -> None:
        """等待事件结束或超时"""
        try:
            await asyncio.wait_for(event.wait(), timeout)
        except asyncio.TimeoutError:
            if not self.future.done():
                self.future.set_exception(TimeoutError("等待超时"))
        except asyncio.CancelledError:
            pass  # 避免报错
        # finally:

    def get_history_chains(self) -> list[list[Comp.BaseMessageComponent]]:
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


class SessionWaiter:
    def __init__(
        self,
        session_filter: SessionFilter,
        session_id: str,
        record_history_chains: bool,
    ) -> None:
        self.session_id = session_id
        self.session_filter = session_filter
        self.handler: (
            Callable[[SessionController, AstrMessageEvent], Awaitable[Any]] | None
        ) = None  # 处理函数

        self.session_controller = SessionController()
        self.record_history_chains = record_history_chains
        """是否记录历史消息链"""

        self._lock = asyncio.Lock()
        """需要保证一个 session 同时只有一个 trigger"""

        self._handler_task: asyncio.Task | None = None
        """当前正在运行的 handler 任务"""

    async def register_wait(
        self,
        handler: Callable[[SessionController, AstrMessageEvent], Awaitable[Any]],
        timeout: int = 30,
    ) -> Any:
        """等待外部输入并处理"""
        self.handler = handler
        USER_SESSIONS[self.session_id] = self

        # 开始一个会话保持事件
        self.session_controller.keep(timeout, reset_timeout=True)

        try:
            return await self.session_controller.future
        except Exception as e:
            await self._cleanup(e)
            raise e
        finally:
            await self._cleanup()

    async def _cleanup(self, error: Exception | None = None) -> None:
        """清理会话。

        这是一个内部私有 async 方法，调用方必须 ``await``。保持 async 是因为取消
        ``_handler_task`` 需要在 ``self._lock`` 保护下进行以避免与 ``trigger`` 竞态；
        不应移除 async 或额外增加同步兼容层（过度工程）。
        """
        USER_SESSIONS.pop(self.session_id, None)
        try:
            FILTERS.remove(self.session_filter)
        except ValueError:
            pass
        # 在锁内取消任务：trigger 在锁内只做创建/取消任务的快速同步操作、不在锁内
        # await handler，且 trigger 锁外 await 期间已释放锁；因此 _cleanup 总能及时
        # 获得锁，两者不会互相阻塞等待对方持有的锁（不会死锁）。
        async with self._lock:
            if self._handler_task and not self._handler_task.done():
                self._handler_task.cancel()
        self.session_controller.stop(error)

    @classmethod
    async def trigger(cls, session_id: str, event: AstrMessageEvent) -> None:
        """外部输入触发会话处理"""
        session = USER_SESSIONS.get(session_id)
        if not session or session.session_controller.future.done():
            return

        task_to_await = None
        async with session._lock:
            if not session.session_controller.future.done():
                if session.record_history_chains:
                    session.session_controller.history_chains.append(
                        [copy.deepcopy(comp) for comp in event.get_messages()],
                    )
                try:
                    # 使用 create_task 跟踪任务，防止超时后 handler 仍然在执行
                    assert session.handler is not None

                    async def _run_handler():
                        # 内层异常处理：把 handler 的普通异常转为 stop(e) 写入 future，
                        # 使 register_wait 能感知；CancelledError 则重新抛出交由外层处理。
                        try:
                            await session.handler(session.session_controller, event)
                        except asyncio.CancelledError:
                            raise  # 重新抛出，让外层的 except asyncio.CancelledError 处理
                        except Exception as e:
                            session.session_controller.stop(e)

                    # 取消上一个可能还在运行的任务
                    if session._handler_task and not session._handler_task.done():
                        session._handler_task.cancel()

                    session._handler_task = asyncio.create_task(_run_handler())
                    task_to_await = session._handler_task
                except Exception as e:
                    session.session_controller.stop(e)
                    return

        # 在锁外等待任务完成，避免死锁：trigger 在锁内只创建任务、不在锁内 await
        # handler，锁已在进入此处前释放；而 _cleanup 仅在锁内取消任务，因此两者不会
        # 互相阻塞等待对方持有的锁。
        if task_to_await:
            try:
                await task_to_await
            except asyncio.CancelledError:
                # 外层只静默处理任务被取消的情况：取消是预期行为（如被 _cleanup 或
                # 后续 trigger 取消），不应上报为异常，也不应写入 future。
                pass
            finally:
                # 清理已完成任务的引用，避免已完成任务残留在 _handler_task 上。
                # 仅当 _handler_task 仍是当前任务时才置 None，防止并发 trigger 已替换它。
                if session._handler_task is task_to_await:
                    session._handler_task = None


def session_waiter(timeout: int = 30, record_history_chains: bool = False):
    """装饰器：自动将函数注册为 SessionWaiter 处理函数，并等待外部输入触发执行。

    :param timeout: 超时时间（秒）
    :param record_history_chain: 是否自动记录历史消息链。可以通过 controller.get_history_chains() 获取。深拷贝。
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

            session_id = session_filter.filter(event)
            FILTERS.append(session_filter)

            waiter = SessionWaiter(session_filter, session_id, record_history_chains)
            return await waiter.register_wait(func, timeout)

        return wrapper

    return decorator
