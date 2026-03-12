"""处理器分发模块。

定义 HandlerDispatcher 类，负责将能力调用分发到具体的处理器函数。
支持参数注入、流式执行、错误处理和生命周期回调。

核心职责：
    - 根据处理器 ID 查找处理器
    - 构建处理器参数（支持类型注解注入）
    - 执行处理器并处理结果
    - 处理异步生成器流式结果
    - 统一的错误处理

参数注入优先级：
    1. 按类型注解注入（支持 Optional[Type]）
    2. 按参数名注入（兼容无类型注解）
    3. 从 legacy_args 注入（命令参数等）

支持的注入类型：
    - MessageEvent: 消息事件
    - Context: 运行时上下文

与旧版对比：
    旧版 HandlerExecutor:
        - 从 star_handlers_registry 获取处理器
        - 直接调用 handler(event, **args)
        - 无参数注入支持
        - 通过 JSON-RPC notification 发送流式结果
        - 错误通过 JSON-RPC error 响应

    新版 HandlerDispatcher:
        - 从 LoadedHandler 映射获取处理器
        - 支持类型注解注入 (MessageEvent, Context)
        - 支持参数名注入 (event, ctx, context)
        - 支持 legacy_args 注入
        - 支持 Optional[Type] 类型
        - 支持默认值
        - 统一的错误处理和 on_error 回调

处理器签名兼容：
    # 旧版签名
    def handler(event: AstrMessageEvent) -> str:
        return "result"

    # 新版签名（类型注入）
    async def handler(event: MessageEvent, ctx: Context) -> None:
        await event.reply("result")

    # 新版签名（名字注入）
    async def handler(event, ctx) -> None:
        await ctx.platform.send(event.session_id, "result")

    # 流式处理器
    async def streaming_handler(event: MessageEvent):
        yield "chunk 1"
        yield "chunk 2"

结果处理：
    - PlainTextResult: 调用 event.reply()
    - str: 调用 event.reply()
    - dict with "text": 调用 event.reply(str(item["text"]))

`HandlerDispatcher` 把运行时收到的 `handler.invoke` 请求转成真实 Python 调用。
它的职责只包括参数注入、legacy 返回值兼容和错误回调；不负责 handler 发现或
远端能力路由。
"""

from __future__ import annotations

import asyncio
import inspect
import typing
from typing import Any, get_type_hints

from ..context import CancelToken, Context
from ..events import MessageEvent, PlainTextResult
from ..star import Star
from .loader import LoadedHandler


class HandlerDispatcher:
    def __init__(self, *, plugin_id: str, peer, handlers: list[LoadedHandler]) -> None:
        self._plugin_id = plugin_id
        self._peer = peer
        self._handlers = {item.descriptor.id: item for item in handlers}
        self._active: dict[str, tuple[asyncio.Task[Any], CancelToken]] = {}

    async def invoke(self, message, cancel_token: CancelToken) -> dict[str, Any]:
        handler_id = str(message.input.get("handler_id", ""))
        loaded = self._handlers.get(handler_id)
        if loaded is None:
            raise LookupError(f"handler not found: {handler_id}")

        ctx = Context(
            peer=self._peer, plugin_id=self._plugin_id, cancel_token=cancel_token
        )
        event = MessageEvent.from_payload(message.input.get("event", {}), context=ctx)
        event.bind_reply_handler(self._create_reply_handler(ctx, event))
        if loaded.legacy_context is not None:
            loaded.legacy_context.bind_runtime_context(ctx)

        # 提取 legacy args 用于兼容旧版 handler 签名
        legacy_args = message.input.get("args") or {}

        task = asyncio.create_task(self._run_handler(loaded, event, ctx, legacy_args))
        self._active[message.id] = (task, cancel_token)
        try:
            await task
            return {}
        finally:
            self._active.pop(message.id, None)

    def _create_reply_handler(self, ctx: Context, event: MessageEvent):
        async def reply(text: str) -> None:
            try:
                await ctx.platform.send(event.session_id, text)
            except TypeError:
                send = getattr(self._peer, "send", None)
                if not callable(send):
                    raise
                result = send(event.session_id, text)
                if inspect.isawaitable(result):
                    await result

        return reply

    async def cancel(self, request_id: str) -> None:
        active = self._active.get(request_id)
        if active is None:
            return
        task, cancel_token = active
        cancel_token.cancel()
        task.cancel()

    async def _run_handler(
        self,
        loaded: LoadedHandler,
        event: MessageEvent,
        ctx: Context,
        legacy_args: dict[str, Any] | None = None,
    ) -> None:
        try:
            result = loaded.callable(
                *self._build_args(loaded.callable, event, ctx, legacy_args)
            )
            if inspect.isasyncgen(result):
                async for item in result:
                    await self._consume_legacy_result(item, event, ctx)
                return
            if inspect.isawaitable(result):
                result = await result
            if result is not None:
                await self._consume_legacy_result(result, event, ctx)
        except Exception as exc:
            await self._handle_error(loaded.owner, exc, event, ctx)
            raise

    def _build_args(
        self,
        handler,
        event: MessageEvent,
        ctx: Context,
        legacy_args: dict[str, Any] | None = None,
    ) -> list[Any]:
        """构建 handler 参数列表。

        注入优先级：
        1. 按类型注解注入（支持 Optional[Type]）
        2. 按参数名注入（兼容无类型注解的情况）
        3. 从 legacy_args 注入（命令参数、regex 捕获组等）

        Args:
            handler: Handler 可调用对象
            event: 消息事件
            ctx: 运行时上下文
            legacy_args: 旧版参数字典

        Returns:
            参数列表
        """
        from loguru import logger

        signature = inspect.signature(handler)
        args: list[Any] = []
        legacy_args = legacy_args or {}

        # 尝试获取类型注解
        type_hints: dict[str, Any] = {}
        try:
            type_hints = get_type_hints(handler)
        except Exception:
            pass

        for parameter in signature.parameters.values():
            if parameter.kind not in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                continue

            injected = None

            # 1. 优先按类型注解注入
            param_type = type_hints.get(parameter.name)
            if param_type is not None:
                injected = self._inject_by_type(param_type, event, ctx)

            # 2. Fallback 按名字注入
            if injected is None:
                if parameter.name == "event":
                    injected = event
                elif parameter.name in {"ctx", "context"}:
                    injected = ctx
                elif parameter.name in legacy_args:
                    injected = legacy_args[parameter.name]

            # 3. 检查是否有默认值
            if injected is None:
                if parameter.default is not parameter.empty:
                    # 有默认值，跳过注入
                    continue
                # 无默认值且无法注入，警告并传 None
                logger.warning(
                    f"Handler '{handler.__name__}': 参数 '{parameter.name}' "
                    f"无法注入（类型: {param_type or '未知'}），将传入 None"
                )
                args.append(None)
            else:
                args.append(injected)

        return args

    def _inject_by_type(
        self, param_type: Any, event: MessageEvent, ctx: Context
    ) -> Any:
        """根据类型注解注入参数。

        支持 Optional[Type] 类型。

        Args:
            param_type: 参数类型注解
            event: 消息事件
            ctx: 运行时上下文

        Returns:
            注入的值，若无法注入则返回 None
        """
        # 处理 Optional[Type] 情况
        origin = typing.get_origin(param_type)
        if origin is typing.Union:
            args = typing.get_args(param_type)
            non_none_types = [a for a in args if a is not type(None)]
            if len(non_none_types) == 1:
                param_type = non_none_types[0]

        # 注入 MessageEvent 及其子类。旧版 compat 事件类型会通过
        # from_message_event() 包装成带便捷方法的对象。
        if param_type is MessageEvent:
            return event
        if isinstance(param_type, type) and issubclass(param_type, MessageEvent):
            if isinstance(event, param_type):
                return event
            factory = getattr(param_type, "from_message_event", None)
            if callable(factory):
                return factory(event)
            return event

        # 注入 Context 及其子类
        if param_type is Context or (
            isinstance(param_type, type) and issubclass(param_type, Context)
        ):
            return ctx

        return None

    async def _consume_legacy_result(
        self,
        item: Any,
        event: MessageEvent,
        ctx: Context | None = None,
    ) -> None:
        from ..api.event.event_result import MessageEventResult
        from ..api.message.chain import MessageChain

        if isinstance(item, MessageEventResult):
            if item.chain and ctx is not None and not item.is_plain_text_only():
                await ctx.platform.send_chain(event.session_id, item.to_payload())
                return
            plain_text = item.get_plain_text()
            if plain_text:
                await event.reply(plain_text)
            return
        if isinstance(item, MessageChain):
            if item.chain and ctx is not None and not item.is_plain_text_only():
                await ctx.platform.send_chain(event.session_id, item.to_payload())
                return
            plain_text = item.get_plain_text()
            if plain_text:
                await event.reply(plain_text)
            return
        if isinstance(item, PlainTextResult):
            await event.reply(item.text)
            return
        if isinstance(item, str):
            await event.reply(item)
            return
        if isinstance(item, dict) and "text" in item:
            await event.reply(str(item["text"]))

    async def _handle_error(
        self,
        owner: Any,
        exc: Exception,
        event: MessageEvent,
        ctx: Context,
    ) -> None:
        if hasattr(owner, "on_error") and callable(owner.on_error):
            result = owner.on_error(exc, event, ctx)
            if inspect.isawaitable(result):
                await result
            return
        await Star().on_error(exc, event, ctx)
