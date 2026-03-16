"""Capability invocation dispatcher.

本模块实现能力调用的分发器，负责：
1. 接收能力调用请求，定位对应的已注册能力
2. 构建调用上下文 (Context)，注入必要的依赖
3. 支持同步和流式两种调用模式
4. 管理活跃调用任务的生命周期和取消

参数注入策略：
按类型注入 Context / CancelToken / dict，或按参数名注入
ctx / context / payload / input / data / cancel_token / token。
若无法匹配则抛出详细的错误信息，帮助开发者定位问题。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import typing
from collections.abc import AsyncIterator, Sequence
from typing import Any, cast, get_type_hints

from loguru import logger

from .._invocation_context import caller_plugin_scope
from .._plugin_logger import PluginLogger
from .._star_runtime import bind_star_runtime
from .._typing_utils import unwrap_optional
from ..context import CancelToken, Context
from ..errors import AstrBotError
from ..events import MessageEvent
from ..star import Star
from ._streaming import StreamExecution
from .loader import LoadedCapability, LoadedLLMTool


class CapabilityDispatcher:
    def __init__(
        self,
        *,
        plugin_id: str,
        peer,
        capabilities: Sequence[LoadedCapability],
        llm_tools: Sequence[LoadedLLMTool] | None = None,
    ) -> None:
        self._plugin_id = plugin_id
        self._peer = peer
        self._capabilities = {item.descriptor.name: item for item in capabilities}
        self._llm_tools: dict[tuple[str, str], LoadedLLMTool] = {}
        try:
            setattr(peer, "_sdk_capability_dispatcher", self)
        except AttributeError:
            logger.warning(
                f"Failed to attach _sdk_capability_dispatcher to peer {peer}, "
                "dynamic LLM tool registration may not work"
            )
        for item in llm_tools or []:
            self._register_llm_tool(item, item.plugin_id or plugin_id)
        self._active: dict[str, tuple[asyncio.Task[Any], CancelToken]] = {}

    def _register_llm_tool(
        self,
        loaded: LoadedLLMTool,
        owner_plugin: str,
    ) -> None:
        self._llm_tools[(owner_plugin, loaded.spec.name)] = loaded
        if loaded.spec.handler_ref and loaded.spec.handler_ref != loaded.spec.name:
            self._llm_tools[(owner_plugin, loaded.spec.handler_ref)] = loaded

    def add_dynamic_llm_tool(
        self,
        *,
        plugin_id: str,
        spec,
        callable_obj,
        owner: Any | None = None,
    ) -> None:
        self.remove_llm_tool(plugin_id, spec.name)
        loaded = LoadedLLMTool(
            spec=spec.model_copy(deep=True),
            callable=callable_obj,
            owner=owner,
            plugin_id=plugin_id,
        )
        self._register_llm_tool(loaded, plugin_id)

    def remove_llm_tool(self, plugin_id: str, name: str) -> bool:
        removed = False
        for key, value in list(self._llm_tools.items()):
            if key[0] != plugin_id:
                continue
            spec_name = str(getattr(value.spec, "name", "")).strip()
            handler_ref = str(getattr(value.spec, "handler_ref", "") or "").strip()
            if name not in {spec_name, handler_ref}:
                continue
            self._llm_tools.pop(key, None)
            removed = True
        return removed

    async def invoke(
        self,
        message,
        cancel_token: CancelToken,
    ) -> dict[str, Any] | StreamExecution:
        if message.capability == "internal.llm_tool.execute":
            return await self._invoke_registered_llm_tool(message, cancel_token)

        loaded = self._capabilities.get(message.capability)
        if loaded is None:
            raise LookupError(f"capability not found: {message.capability}")

        plugin_id = self._resolve_plugin_id(loaded)
        ctx = Context(
            peer=self._peer,
            plugin_id=plugin_id,
            cancel_token=cancel_token,
        )
        bound_logger = cast(PluginLogger, ctx.logger).bind(
            plugin_id=plugin_id,
            request_id=message.id,
            capability=message.capability,
            session_id=self._logger_session_id(dict(message.input)),
            event_type=self._logger_event_type(dict(message.input)),
        )
        ctx.logger = bound_logger

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

    async def _invoke_registered_llm_tool(
        self,
        message,
        cancel_token: CancelToken,
    ) -> dict[str, Any]:
        payload = dict(message.input)
        plugin_id = str(payload.get("plugin_id") or self._plugin_id)
        tool_name = str(payload.get("tool_name", ""))
        handler_ref = str(payload.get("handler_ref") or tool_name)
        loaded = self._llm_tools.get((plugin_id, handler_ref))
        if loaded is None:
            loaded = self._llm_tools.get((plugin_id, tool_name))
        if loaded is None:
            raise LookupError(f"llm tool not found: {plugin_id}:{tool_name}")

        event_payload = payload.get("event")
        ctx = Context(
            peer=self._peer,
            plugin_id=plugin_id,
            cancel_token=cancel_token,
            source_event_payload=event_payload
            if isinstance(event_payload, dict)
            else None,
        )
        bound_logger = cast(PluginLogger, ctx.logger).bind(
            plugin_id=plugin_id,
            request_id=message.id,
            capability="internal.llm_tool.execute",
            session_id=self._logger_session_id(payload),
            event_type=self._logger_event_type(payload),
        )
        ctx.logger = bound_logger
        event = MessageEvent.from_payload(
            event_payload if isinstance(event_payload, dict) else {},
            context=ctx,
        )
        self._bind_event_reply_handler(ctx, event)
        tool_args = payload.get("tool_args")
        normalized_args = dict(tool_args) if isinstance(tool_args, dict) else {}

        with caller_plugin_scope(plugin_id):
            task = asyncio.create_task(
                self._run_registered_llm_tool(loaded, event, ctx, normalized_args)
            )
        self._active[message.id] = (task, cancel_token)
        try:
            return await task
        finally:
            self._active.pop(message.id, None)

    def _bind_event_reply_handler(self, ctx: Context, event: MessageEvent) -> None:
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

        event.bind_reply_handler(reply)

    async def _run_registered_llm_tool(
        self,
        loaded: LoadedLLMTool,
        event: MessageEvent,
        ctx: Context,
        tool_args: dict[str, Any],
    ) -> dict[str, Any]:
        owner = loaded.owner if isinstance(loaded.owner, Star) else None
        with bind_star_runtime(owner, ctx):
            result = loaded.callable(
                *self._build_tool_args(
                    loaded.callable,
                    event,
                    ctx,
                    tool_args,
                )
            )
            if inspect.isasyncgen(result):
                raise AstrBotError.protocol_error(
                    "SDK LLM tool must return awaitable result, async generator is unsupported"
                )
            if inspect.isawaitable(result):
                result = await result
        if result is None:
            # content=None means the tool completed successfully but produced no
            # textual payload. The core bridge preserves this as a real None.
            return {"content": None, "success": True}
        if isinstance(result, dict):
            return {
                "content": json.dumps(result, ensure_ascii=False, default=str),
                "success": True,
            }
        return {"content": str(result), "success": True}

    def _build_tool_args(
        self,
        handler,
        event: MessageEvent,
        ctx: Context,
        tool_args: dict[str, Any],
    ) -> list[Any]:
        signature = inspect.signature(handler)
        args: list[Any] = []
        type_hints: dict[str, Any] = {}
        try:
            type_hints = get_type_hints(handler)
        except Exception:
            type_hints = {}

        for parameter in signature.parameters.values():
            if parameter.kind not in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                continue

            injected = None
            param_type = type_hints.get(parameter.name)
            if param_type is not None:
                injected = self._inject_tool_by_type(param_type, event, ctx)
            if injected is None:
                if parameter.name == "event":
                    injected = event
                elif parameter.name in {"ctx", "context"}:
                    injected = ctx
                elif parameter.name in tool_args:
                    injected = tool_args[parameter.name]
            if injected is None:
                if parameter.default is not parameter.empty:
                    continue
                raise TypeError(
                    f"SDK LLM tool '{getattr(handler, '__name__', repr(handler))}' missing required argument '{parameter.name}'"
                )
            args.append(injected)
        return args

    def _inject_tool_by_type(
        self,
        param_type: Any,
        event: MessageEvent,
        ctx: Context,
    ) -> Any:
        param_type, _is_optional = unwrap_optional(param_type)

        if param_type is Context or (
            isinstance(param_type, type) and issubclass(param_type, Context)
        ):
            return ctx
        if param_type is MessageEvent or (
            isinstance(param_type, type) and issubclass(param_type, MessageEvent)
        ):
            return event
        return None

    def _resolve_plugin_id(self, loaded: LoadedCapability) -> str:
        if loaded.plugin_id:
            return loaded.plugin_id
        return self._plugin_id

    @staticmethod
    def _logger_session_id(payload: dict[str, Any]) -> str:
        if isinstance(payload.get("event"), dict):
            return str(payload["event"].get("session_id", ""))
        return str(payload.get("session", ""))

    @staticmethod
    def _logger_event_type(payload: dict[str, Any]) -> str:
        if isinstance(payload.get("event"), dict):
            event_payload = payload["event"]
            return str(
                event_payload.get("event_type")
                or event_payload.get("type")
                or event_payload.get("message_type")
                or "message"
            )
        if payload.get("session") is not None:
            return "capability"
        return "capability"

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
        param_type, _is_optional = unwrap_optional(param_type)
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
            f"{self._callable_signature(handler)}。"
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

    @staticmethod
    def _callable_signature(handler) -> str:
        try:
            return str(inspect.signature(handler))
        except (TypeError, ValueError):
            return "(?)"


__all__ = ["CapabilityDispatcher"]
