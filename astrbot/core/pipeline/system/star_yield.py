"""Star 插件 yield 模式兼容层。

提供 StarYieldDriver 和 StarHandlerAdapter，用于在新架构中
完整支持旧版 Star 插件的 AsyncGenerator (yield) 模式。

yield 模式允许插件：
1. 多次 yield 发送中间消息
2. yield ProviderRequest 进行 LLM 请求
3. 通过 try/except 处理异常
4. 通过 event.stop_event() 控制流程
"""

from __future__ import annotations

import inspect
import traceback
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from astrbot.core import logger
from astrbot.core.message.message_event_result import CommandResult, MessageEventResult

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.provider.entities import ProviderRequest


@dataclass
class YieldDriverResult:
    """yield 驱动执行结果"""

    messages_sent: int = 0
    llm_requests: list[Any] = field(default_factory=list)
    stopped: bool = False
    error: Exception | None = None


class StarYieldDriver:
    """Star 插件 yield 模式驱动器

    处理 AsyncGenerator 返回的 handler，支持：
    1. 多次 yield 发送中间消息
    2. yield ProviderRequest 进行 LLM 请求
    3. 异常传播回 generator (athrow)
    4. event.stop_event() 控制流程

    从原 PluginDispatcher._drive_async_generator 和
    context_utils.call_handler 提炼整合。
    """

    def __init__(
        self,
        send_callback: Callable,
        provider_request_callback: Callable[
            [AstrMessageEvent, ProviderRequest], Awaitable[None]
        ]
        | None = None,
    ) -> None:
        """
        Args:
            send_callback: async def (event: AstrMessageEvent) -> None
                           发送消息的回调，由外部提供
        """
        self._send = send_callback
        self._on_provider_request = provider_request_callback

    async def drive(
        self,
        generator: AsyncGenerator,
        event: AstrMessageEvent,
    ) -> YieldDriverResult:
        """驱动 AsyncGenerator 执行

        Args:
            generator: 插件 handler 返回的 AsyncGenerator
            event: 消息事件

        Returns:
            YieldDriverResult 包含执行统计
        """
        result = YieldDriverResult()

        while True:
            try:
                yielded = await generator.asend(None)
            except StopAsyncIteration:
                break
            except Exception as e:
                result.error = e
                logger.error(traceback.format_exc())
                break

            try:
                await self._handle_yielded(yielded, event, result)
            except Exception as e:
                # 将异常传回 generator，让插件有机会 catch
                try:
                    yielded = await generator.athrow(type(e), e, e.__traceback__)
                except StopAsyncIteration:
                    break
                except Exception as inner_e:
                    result.error = inner_e
                    logger.error(traceback.format_exc())
                    break
                await self._handle_yielded(yielded, event, result)

            if event.is_stopped():
                result.stopped = True
                break

        return result

    async def _handle_yielded(
        self,
        yielded: Any,
        event: AstrMessageEvent,
        result: YieldDriverResult,
    ) -> None:
        """处理 yield 出来的值"""
        from astrbot.core.provider.entities import ProviderRequest

        if yielded is None:
            # yield 空值 — 检查 event 上是否已有 result
            if event.get_result():
                await self._send_and_clear(event, result)
            return

        if isinstance(yielded, ProviderRequest):
            # LLM 请求
            result.llm_requests.append(yielded)
            event.set_extra("has_provider_request", True)
            event.set_extra("provider_request", yielded)
            if self._on_provider_request:
                await self._on_provider_request(event, yielded)
            return

        if isinstance(yielded, MessageEventResult | CommandResult):
            event.set_result(yielded)
            await self._send_and_clear(event, result)
            return

        if isinstance(yielded, str):
            event.set_result(MessageEventResult().message(yielded))
            await self._send_and_clear(event, result)
            return

        # 未知类型 — 检查 event 上是否有 result (插件可能直接 set_result)
        if event.get_result():
            await self._send_and_clear(event, result)

    async def _send_and_clear(
        self,
        event: AstrMessageEvent,
        result: YieldDriverResult,
    ) -> None:
        """发送消息并清理 result"""
        if event.get_result():
            await self._send(event)
            result.messages_sent += 1
            event.clear_result()


class StarHandlerAdapter:
    """Star Handler 适配器

    统一处理 async def 和 async generator 两种 handler 形式。
    自动检测 handler 返回类型并选择合适的执行方式。
    """

    def __init__(self, yield_driver: StarYieldDriver) -> None:
        self._driver = yield_driver

    async def invoke(
        self,
        handler: Callable,
        event: AstrMessageEvent,
        *args: Any,
        **kwargs: Any,
    ) -> YieldDriverResult:
        """调用 handler

        自动检测 handler 类型：
        - AsyncGenerator: 使用 yield driver 驱动
        - Coroutine: 直接 await

        Returns:
            YieldDriverResult
        """
        result = YieldDriverResult()

        try:
            ready_to_call = handler(event, *args, **kwargs)
        except TypeError:
            logger.error("处理函数参数不匹配，请检查 handler 的定义。", exc_info=True)
            result.error = TypeError("handler parameter mismatch")
            return result

        if ready_to_call is None:
            return result

        if inspect.isasyncgen(ready_to_call):
            return await self._driver.drive(ready_to_call, event)

        if inspect.iscoroutine(ready_to_call):
            try:
                ret = await ready_to_call
                if ret is not None:
                    await self._driver._handle_yielded(ret, event, result)
            except Exception as e:
                result.error = e
                logger.error(traceback.format_exc())

        return result
