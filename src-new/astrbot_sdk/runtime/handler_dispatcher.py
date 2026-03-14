"""处理器分发模块。

定义 HandlerDispatcher 类，负责将能力调用分发到具体的处理器函数。
支持参数注入、流式执行、错误处理。

核心职责：
    - 根据处理器 ID 查找处理器
    - 构建处理器参数（支持类型注解注入）
    - 执行处理器并处理结果
    - 处理异步生成器流式结果
    - 统一的错误处理

参数注入优先级：
    1. 按类型注解注入（支持 Optional[Type]）
    2. 按参数名注入（兼容无类型注解）
    3. 从 args 注入（命令参数等）

支持的注入类型：
    - MessageEvent: 消息事件
    - Context: 运行时上下文
"""

from __future__ import annotations

import asyncio
import inspect
import typing
from collections.abc import AsyncIterator
from typing import Any, get_type_hints

from .._invocation_context import caller_plugin_scope
from ..context import CancelToken, Context
from ..errors import AstrBotError
from ..events import MessageEvent
from ..star import Star
from .capability_router import StreamExecution
from .loader import LoadedCapability, LoadedHandler


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

        plugin_id = self._resolve_plugin_id(loaded)
        ctx = Context(peer=self._peer, plugin_id=plugin_id, cancel_token=cancel_token)
        event = MessageEvent.from_payload(message.input.get("event", {}), context=ctx)
        event.bind_reply_handler(self._create_reply_handler(ctx, event))

        # 提取 args 用于兼容 handler 签名
        args = message.input.get("args") or {}

        with caller_plugin_scope(plugin_id):
            task = asyncio.create_task(self._run_handler(loaded, event, ctx, args))
        self._active[message.id] = (task, cancel_token)
        try:
            await task
            return {}
        finally:
            self._active.pop(message.id, None)

    def _resolve_plugin_id(self, loaded: LoadedHandler) -> str:
        if loaded.plugin_id:
            return loaded.plugin_id
        handler_id = getattr(loaded.descriptor, "id", "")
        if isinstance(handler_id, str) and ":" in handler_id:
            return handler_id.split(":", 1)[0]
        return self._plugin_id

    def _create_reply_handler(self, ctx: Context, event: MessageEvent):
        async def reply(text: str) -> None:
            try:
                await ctx.platform.send(event.session_ref or event.session_id, text)
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
        args: dict[str, Any] | None = None,
    ) -> None:
        try:
            result = loaded.callable(
                *self._build_args(loaded.callable, event, ctx, args)
            )
            if inspect.isasyncgen(result):
                async for item in result:
                    await self._send_result(item, event, ctx)
                return
            if inspect.isawaitable(result):
                result = await result
            if result is not None:
                await self._send_result(result, event, ctx)
        except Exception as exc:
            await self._handle_error(
                loaded.owner,
                exc,
                event,
                ctx,
                handler_name=loaded.callable.__name__,
                plugin_id=self._resolve_plugin_id(loaded),
            )
            raise

    def _build_args(
        self,
        handler,
        event: MessageEvent,
        ctx: Context,
        args: dict[str, Any] | None = None,
    ) -> list[Any]:
        """构建 handler 参数列表。"""
        from loguru import logger

        signature = inspect.signature(handler)
        injected_args: list[Any] = []
        args = args or {}

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
                elif parameter.name in args:
                    injected = args[parameter.name]

            # 3. 检查是否有默认值
            if injected is None:
                if parameter.default is not parameter.empty:
                    continue
                logger.error(
                    "Handler '{}' 的必填参数 '{}' 无法注入",
                    handler.__name__,
                    parameter.name,
                )
                raise TypeError(
                    f"handler '{handler.__name__}' 的必填参数 "
                    f"'{parameter.name}' 无法注入"
                )
            else:
                injected_args.append(injected)

        return injected_args

    def _inject_by_type(
        self, param_type: Any, event: MessageEvent, ctx: Context
    ) -> Any:
        """根据类型注解注入参数。"""
        # 处理 Optional[Type] 情况
        origin = typing.get_origin(param_type)
        if origin is typing.Union:
            type_args = typing.get_args(param_type)
            non_none_types = [a for a in type_args if a is not type(None)]
            if len(non_none_types) == 1:
                param_type = non_none_types[0]

        # 注入 MessageEvent 及其子类
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

    async def _send_result(
        self,
        item: Any,
        event: MessageEvent,
        ctx: Context | None = None,
    ) -> bool:
        """发送处理器结果。"""
        if isinstance(item, str):
            await event.reply(item)
            return True
        if isinstance(item, dict) and "text" in item:
            await event.reply(str(item["text"]))
            return True
        # 支持带 text 属性的对象
        text = getattr(item, "text", None)
        if isinstance(text, str):
            await event.reply(text)
            return True
        return False

    async def _handle_error(
        self,
        owner: Any,
        exc: Exception,
        event: MessageEvent,
        ctx: Context,
        *,
        handler_name: str = "",
        plugin_id: str | None = None,
    ) -> None:
        if hasattr(owner, "on_error") and callable(owner.on_error):
            result = owner.on_error(exc, event, ctx)
            if inspect.isawaitable(result):
                await result
            return
        await Star().on_error(exc, event, ctx)


class CapabilityDispatcher:
    def __init__(
        self,
        *,
        plugin_id: str,
        peer,
        capabilities: list[LoadedCapability],
    ) -> None:
        self._plugin_id = plugin_id
        self._peer = peer
        self._capabilities = {item.descriptor.name: item for item in capabilities}
        self._active: dict[str, tuple[asyncio.Task[Any], CancelToken]] = {}

    async def invoke(
        self,
        message,
        cancel_token: CancelToken,
    ) -> dict[str, Any] | StreamExecution:
        loaded = self._capabilities.get(message.capability)
        if loaded is None:
            raise LookupError(f"capability not found: {message.capability}")

        plugin_id = self._resolve_plugin_id(loaded)
        ctx = Context(
            peer=self._peer,
            plugin_id=plugin_id,
            cancel_token=cancel_token,
        )

        with caller_plugin_scope(plugin_id):
            task = asyncio.create_task(
                self._run_capability(
                    loaded,
                    payload=dict(message.input),
                    ctx=ctx,
                    cancel_token=cancel_token,
                    stream=bool(message.stream),
                )
            )
        self._active[message.id] = (task, cancel_token)
        try:
            return await task
        finally:
            self._active.pop(message.id, None)

    def _resolve_plugin_id(self, loaded: LoadedCapability) -> str:
        if loaded.plugin_id:
            return loaded.plugin_id
        return self._plugin_id

    async def cancel(self, request_id: str) -> None:
        active = self._active.get(request_id)
        if active is None:
            return
        task, cancel_token = active
        cancel_token.cancel()
        task.cancel()

    async def _run_capability(
        self,
        loaded: LoadedCapability,
        *,
        payload: dict[str, Any],
        ctx: Context,
        cancel_token: CancelToken,
        stream: bool,
    ) -> dict[str, Any] | StreamExecution:
        result = loaded.callable(
            *self._build_args(loaded.callable, payload, ctx, cancel_token)
        )
        if stream:
            if inspect.isasyncgen(result):
                return StreamExecution(
                    iterator=self._iterate_generator(result),
                    finalize=lambda chunks: {"items": chunks},
                )
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, StreamExecution):
                return result
            raise AstrBotError.protocol_error(
                "stream=true 的插件 capability 必须返回 async generator 或 StreamExecution"
            )

        if inspect.isasyncgen(result):
            raise AstrBotError.protocol_error(
                "stream=false 的插件 capability 不能返回 async generator"
            )
        if inspect.isawaitable(result):
            result = await result
        return self._normalize_output(result)

    def _build_args(
        self,
        handler,
        payload: dict[str, Any],
        ctx: Context,
        cancel_token: CancelToken,
    ) -> list[Any]:
        signature = inspect.signature(handler)
        args: list[Any] = []

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
            param_type = type_hints.get(parameter.name)
            if param_type is not None:
                injected = self._inject_by_type(param_type, payload, ctx, cancel_token)

            if injected is None:
                if parameter.name in {"ctx", "context"}:
                    injected = ctx
                elif parameter.name in {"payload", "input", "data"}:
                    injected = payload
                elif parameter.name in {"cancel_token", "token"}:
                    injected = cancel_token

            if injected is None:
                if parameter.default is not parameter.empty:
                    continue
                raise TypeError(
                    f"capability '{handler.__name__}' 的必填参数 "
                    f"'{parameter.name}' 无法注入"
                )
            args.append(injected)

        return args

    def _inject_by_type(
        self,
        param_type: Any,
        payload: dict[str, Any],
        ctx: Context,
        cancel_token: CancelToken,
    ) -> Any:
        origin = typing.get_origin(param_type)
        if origin is typing.Union:
            type_args = typing.get_args(param_type)
            non_none_types = [item for item in type_args if item is not type(None)]
            if len(non_none_types) == 1:
                param_type = non_none_types[0]
                origin = typing.get_origin(param_type)

        if param_type is Context or (
            isinstance(param_type, type) and issubclass(param_type, Context)
        ):
            return ctx
        if param_type is CancelToken or (
            isinstance(param_type, type) and issubclass(param_type, CancelToken)
        ):
            return cancel_token
        if param_type is dict or origin is dict:
            return payload
        return None

    async def _iterate_generator(
        self,
        generator: AsyncIterator[Any],
    ) -> AsyncIterator[dict[str, Any]]:
        async for item in generator:
            yield self._normalize_chunk(item)

    def _normalize_chunk(self, item: Any) -> dict[str, Any]:
        output = self._normalize_output(item)
        if output:
            return output
        return {"ok": True}

    def _normalize_output(self, result: Any) -> dict[str, Any]:
        if result is None:
            return {}
        if isinstance(result, dict):
            return result
        model_dump = getattr(result, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        raise AstrBotError.invalid_input("插件 capability 必须返回 dict 或可序列化对象")
