"""
会话控制
"""

import abc
import asyncio
import time
import functools
import copy
import astrbot.core.message.components as Comp
from typing import Dict, Any, Callable, Awaitable, List
from astrbot.core.platform import AstrMessageEvent

USER_SESSIONS: Dict[str, "SessionWaiter"] = {}  # 存储 SessionWaiter 实例
FILTERS: List["SessionFilter"] = []  # 存储 SessionFilter 实例


class SessionController:
    """
    控制一个 Session 是否已经结束
    """

    def __init__(self):
        self.future = asyncio.Future()
        self.current_event: asyncio.Event = None
        """当前正在等待的所用的异步事件"""
        self.ts: float = None
        """上次保持(keep)开始时的时间"""
        self.timeout: float | int = None
        """上次保持(keep)开始时的超时时间"""

        self.history_chains: List[List[Comp.BaseMessageComponent]] = []

    def stop(self, error: Exception = None):
        """立即结束这个会话"""
        if not self.future.done():
            if error:
                self.future.set_exception(error)
            else:
                self.future.set_result(None)

    def keep(self, timeout: float | int = 0, reset_timeout=False):
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

    async def _holding(self, event: asyncio.Event, timeout: int):
        """等待事件结束或超时"""
        try:
            await asyncio.wait_for(event.wait(), timeout)
        except asyncio.TimeoutError:
            if not self.future.done():
                self.future.set_exception(TimeoutError("等待超时"))
        except asyncio.CancelledError:
            pass  # 避免报错
        # finally:

    def get_history_chains(self) -> List[List[Comp.BaseMessageComponent]]:
        """获取历史消息链"""
        return self.history_chains


class SessionFilter:
    """如何界定一个会话"""

    @abc.abstractmethod
    def filter(self, event: AstrMessageEvent) -> str:
        """根据事件返回一个会话标识符"""
        pass


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
    ):
        self.session_id = session_id
        self.session_filter = session_filter
        self.handler: Callable[[str], Awaitable[Any]] | None = None  # 处理函数

        self.session_controller = SessionController()
        self.record_history_chains = record_history_chains
        """是否记录历史消息链"""

        self._lock = asyncio.Lock()
        """需要保证一个 session 同时只有一个 trigger"""

    async def register_wait(
        self, handler: Callable[[str], Awaitable[Any]], timeout: int = 30
    ) -> Any:
        """等待外部输入并处理"""
        self.handler = handler
        USER_SESSIONS[self.session_id] = self

        # 开始一个会话保持事件
        self.session_controller.keep(timeout, reset_timeout=True)

        try:
            return await self.session_controller.future
        except Exception as e:
            self._cleanup(e)
            raise e
        finally:
            self._cleanup()

    def _cleanup(self, error: Exception = None):
        """清理会话"""
        USER_SESSIONS.pop(self.session_id, None)
        try:
            FILTERS.remove(self.session_filter)
        except ValueError:
            pass
        self.session_controller.stop(error)

    @classmethod
    async def trigger(cls, session_id: str, event: AstrMessageEvent):
        """外部输入触发会话处理"""
        session = USER_SESSIONS.get(session_id, None)
        if not session or session.session_controller.future.done():
            return

        async with session._lock:
            if not session.session_controller.future.done():
                if session.record_history_chains:
                    session.session_controller.history_chains.append(
                        [copy.deepcopy(comp) for comp in event.get_messages()]
                    )
                try:
                    # TODO: 这里使用 create_task，跟踪 task，防止超时后这里 handler 仍然在执行
                    await session.handler(session.session_controller, event)
                except Exception as e:
                    session.session_controller.stop(e)


def session_waiter(timeout: int = 30, record_history_chains: bool = False):
    """
    装饰器：自动将函数注册为 SessionWaiter 处理函数，并等待外部输入触发执行。

    :param timeout: 超时时间（秒）
    :param record_history_chain: 是否自动记录历史消息链。可以通过 controller.get_history_chains() 获取。深拷贝。
    """

    def decorator(func: Callable[[str], Awaitable[Any]]):
        @functools.wraps(func)
        async def wrapper(
            event: AstrMessageEvent,
            session_filter: SessionFilter = None,
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
