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
import re
import shlex
import typing
from collections.abc import AsyncIterator
from typing import Any, get_type_hints

from .._invocation_context import caller_plugin_scope
from ..context import CancelToken, Context
from ..errors import AstrBotError
from ..events import MessageEvent
from ..protocol.descriptors import CommandTrigger, MessageTrigger
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
        raw_args = message.input.get("args") or {}
        args = dict(raw_args) if isinstance(raw_args, dict) else {}
        if not args:
            args = self._derive_args(loaded, event)

        with caller_plugin_scope(plugin_id):
            task = asyncio.create_task(self._run_handler(loaded, event, ctx, args))
        self._active[message.id] = (task, cancel_token)
        try:
            return await task
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
    ) -> dict[str, Any]:
        summary = {"sent_message": False, "stop": False, "call_llm": False}
        try:
            result = loaded.callable(
                *self._build_args(
                    loaded.callable,
                    event,
                    ctx,
                    args,
                    plugin_id=self._resolve_plugin_id(loaded),
                    handler_ref=loaded.descriptor.id,
                )
            )
            if inspect.isasyncgen(result):
                async for item in result:
                    self._merge_handler_summary(
                        summary,
                        await self._handle_result_item(item, event, ctx),
                    )
                return summary
            if inspect.isawaitable(result):
                result = await result
            if result is not None:
                self._merge_handler_summary(
                    summary,
                    await self._handle_result_item(result, event, ctx),
                )
            return summary
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

    def _derive_args(
        self,
        loaded: LoadedHandler,
        event: MessageEvent,
    ) -> dict[str, Any]:
        trigger = loaded.descriptor.trigger
        if isinstance(trigger, CommandTrigger):
            for command_name in [trigger.command, *trigger.aliases]:
                remainder = self._match_command_name(event.text, command_name)
                if remainder is not None:
                    return self._build_command_args(loaded.callable, remainder)
            return {}
        if isinstance(trigger, MessageTrigger) and trigger.regex:
            match = re.search(trigger.regex, event.text)
            if match is None:
                return {}
            return self._build_regex_args(loaded.callable, match)
        return {}

    def _build_args(
        self,
        handler,
        event: MessageEvent,
        ctx: Context,
        args: dict[str, Any] | None = None,
        *,
        plugin_id: str | None = None,
        handler_ref: str | None = None,
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
                    self._format_handler_injection_error(
                        handler=handler,
                        parameter_name=parameter.name,
                        plugin_id=plugin_id,
                        handler_ref=handler_ref,
                        args=args,
                    )
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

    def _format_handler_injection_error(
        self,
        *,
        handler,
        parameter_name: str,
        plugin_id: str | None,
        handler_ref: str | None,
        args: dict[str, Any],
    ) -> str:
        plugin_text = plugin_id or self._plugin_id
        target = handler_ref or getattr(handler, "__name__", "<anonymous>")
        arg_keys = sorted(str(key) for key in args.keys())
        arg_keys_text = ", ".join(arg_keys) if arg_keys else "<none>"
        return (
            f"插件 '{plugin_text}' 的 handler '{target}' 参数注入失败："
            f"必填参数 '{parameter_name}' 无法注入。"
            f"签名: {getattr(handler, '__name__', '<anonymous>')}"
            f"{self._callable_signature(handler)}。"
            "当前支持按类型注入 MessageEvent / Context，"
            "按参数名注入 event / ctx / context，"
            f"以及 args 中现有键：{arg_keys_text}。"
        )

    @staticmethod
    def _callable_signature(handler) -> str:
        try:
            return str(inspect.signature(handler))
        except (TypeError, ValueError):
            return "(...)"

    async def _handle_result_item(
        self,
        item: Any,
        event: MessageEvent,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        sent_message = await self._send_result(item, event, ctx)
        if isinstance(item, dict):
            return {
                "sent_message": sent_message,
                "stop": bool(item.get("stop", False)),
                "call_llm": bool(item.get("call_llm", False)),
            }
        return {
            "sent_message": sent_message,
            "stop": False,
            "call_llm": False,
        }

    @staticmethod
    def _merge_handler_summary(
        target: dict[str, Any],
        source: dict[str, Any],
    ) -> None:
        target["sent_message"] = bool(target.get("sent_message")) or bool(
            source.get("sent_message")
        )
        target["stop"] = bool(target.get("stop")) or bool(source.get("stop"))
        target["call_llm"] = bool(target.get("call_llm")) or bool(
            source.get("call_llm")
        )

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

    @staticmethod
    def _match_command_name(text: str, command_name: str) -> str | None:
        normalized = text.strip()
        if normalized == command_name:
            return ""
        if normalized.startswith(f"{command_name} "):
            return normalized[len(command_name) :].strip()
        return None

    @classmethod
    def _build_command_args(cls, handler, remainder: str) -> dict[str, Any]:
        names = cls._legacy_arg_parameter_names(handler)
        if not names or not remainder:
            return {}
        if len(names) == 1:
            return {names[0]: remainder}
        parts = cls._split_command_remainder(remainder)
        return {
            name: parts[index] for index, name in enumerate(names) if index < len(parts)
        }

    @classmethod
    def _build_regex_args(cls, handler, match: re.Match[str]) -> dict[str, Any]:
        named = {
            key: value for key, value in match.groupdict().items() if value is not None
        }
        names = [
            name
            for name in cls._legacy_arg_parameter_names(handler)
            if name not in named
        ]
        positional = [value for value in match.groups() if value is not None]
        for index, value in enumerate(positional):
            if index >= len(names):
                break
            named[names[index]] = value
        return named

    @staticmethod
    def _split_command_remainder(remainder: str) -> list[str]:
        try:
            return shlex.split(remainder)
        except ValueError:
            return remainder.split()

    @classmethod
    def _legacy_arg_parameter_names(cls, handler) -> list[str]:
        try:
            signature = inspect.signature(handler)
        except (TypeError, ValueError):
            return []
        try:
            type_hints = get_type_hints(handler)
        except Exception:
            type_hints = {}
        names: list[str] = []
        for parameter in signature.parameters.values():
            if parameter.kind not in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                continue
            if cls._is_injected_parameter(
                parameter.name, type_hints.get(parameter.name)
            ):
                continue
            names.append(parameter.name)
        return names

    @classmethod
    def _is_injected_parameter(cls, name: str, annotation: Any) -> bool:
        if name in {"event", "ctx", "context"}:
            return True
        normalized = cls._unwrap_optional(annotation)
        if normalized is None:
            return False
        if normalized is Context or normalized is MessageEvent:
            return True
        if isinstance(normalized, type) and issubclass(
            normalized,
            (Context, MessageEvent),
        ):
            return True
        return False

    @staticmethod
    def _unwrap_optional(annotation: Any) -> Any:
        if annotation is None:
            return None
        origin = typing.get_origin(annotation)
        if origin is typing.Union:
            options = [
                item for item in typing.get_args(annotation) if item is not type(None)
            ]
            if len(options) == 1:
                return options[0]
        return annotation

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
            *self._build_args(
                loaded.callable,
                payload,
                ctx,
                cancel_token,
                plugin_id=self._resolve_plugin_id(loaded),
                capability_name=loaded.descriptor.name,
            )
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
        *,
        plugin_id: str | None = None,
        capability_name: str | None = None,
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
                    self._format_capability_injection_error(
                        handler=handler,
                        parameter_name=parameter.name,
                        plugin_id=plugin_id,
                        capability_name=capability_name,
                        payload=payload,
                    )
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

    def _format_capability_injection_error(
        self,
        *,
        handler,
        parameter_name: str,
        plugin_id: str | None,
        capability_name: str | None,
        payload: dict[str, Any],
    ) -> str:
        plugin_text = plugin_id or self._plugin_id
        target = capability_name or getattr(handler, "__name__", "<anonymous>")
        payload_keys = sorted(str(key) for key in payload.keys())
        payload_keys_text = ", ".join(payload_keys) if payload_keys else "<none>"
        return (
            f"插件 '{plugin_text}' 的 capability '{target}' 参数注入失败："
            f"必填参数 '{parameter_name}' 无法注入。"
            f"签名: {getattr(handler, '__name__', '<anonymous>')}"
            f"{HandlerDispatcher._callable_signature(handler)}。"
            "当前支持按类型注入 Context / CancelToken / dict，"
            "按参数名注入 ctx / context / payload / input / data / cancel_token / token，"
            f"以及 payload 中现有键：{payload_keys_text}。"
        )

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
