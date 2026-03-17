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
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast, get_type_hints

from loguru import logger

from .._command_model import (
    parse_command_model_remainder,
    resolve_command_model_param,
)
from .._invocation_context import caller_plugin_scope
from .._plugin_logger import PluginLogger
from .._star_runtime import bind_star_runtime
from .._typing_utils import unwrap_optional
from ..context import CancelToken, Context
from ..conversation import (
    DEFAULT_BUSY_MESSAGE,
    ConversationClosed,
    ConversationReplaced,
    ConversationSession,
    ConversationState,
)
from ..events import MessageEvent
from ..filters import LocalFilterBinding
from ..message_components import BaseMessageComponent
from ..message_result import MessageChain, MessageEventResult, coerce_message_chain
from ..protocol.descriptors import (
    CommandTrigger,
    MessageTrigger,
    ParamSpec,
    ScheduleTrigger,
)
from ..schedule import ScheduleContext
from ..session_waiter import SessionWaiterManager
from ..star import Star
from .capability_dispatcher import CapabilityDispatcher
from .limiter import LimiterEngine
from .loader import LoadedHandler


@dataclass(slots=True)
class _ActiveConversation:
    session: ConversationSession
    task: asyncio.Task[Any]


class HandlerDispatcher:
    def __init__(
        self, *, plugin_id: str, peer, handlers: Sequence[LoadedHandler]
    ) -> None:
        self._plugin_id = plugin_id
        self._peer = peer
        self._handlers = {item.descriptor.id: item for item in handlers}
        self._active: dict[str, tuple[asyncio.Task[Any], CancelToken]] = {}
        self._session_waiters = SessionWaiterManager(plugin_id=plugin_id, peer=peer)
        self._limiter = LimiterEngine()
        self._conversations: dict[str, _ActiveConversation] = {}
        try:
            setattr(peer, "_session_waiter_manager", self._session_waiters)
        except AttributeError:
            logger.warning(
                f"Failed to attach _session_waiter_manager to peer {peer}, "
                "some features may not work as expected"
            )

    async def invoke(self, message, cancel_token: CancelToken) -> dict[str, Any]:
        handler_id = str(message.input.get("handler_id", ""))
        if handler_id == "__sdk_session_waiter__":
            plugin_id = self._plugin_id
            ctx = Context(
                peer=self._peer, plugin_id=plugin_id, cancel_token=cancel_token
            )
            event = MessageEvent.from_payload(
                message.input.get("event", {}), context=ctx
            )
            event.bind_reply_handler(self._create_reply_handler(ctx, event))
            task = asyncio.create_task(self._session_waiters.dispatch(event))
            self._active[message.id] = (task, cancel_token)
            try:
                return await task
            finally:
                self._active.pop(message.id, None)

        loaded = self._handlers.get(handler_id)
        if loaded is None:
            raise LookupError(f"handler not found: {handler_id}")

        plugin_id = self._resolve_plugin_id(loaded)
        event_payload = message.input.get("event", {})
        ctx = Context(
            peer=self._peer,
            plugin_id=plugin_id,
            cancel_token=cancel_token,
            source_event_payload=event_payload
            if isinstance(event_payload, dict)
            else None,
        )
        event = MessageEvent.from_payload(event_payload, context=ctx)
        bound_logger = cast(PluginLogger, ctx.logger).bind(
            plugin_id=plugin_id,
            request_id=message.id,
            handler_ref=handler_id,
            session_id=event.session_id,
            event_type=str(
                event_payload.get("event_type")
                or event_payload.get("type")
                or event.message_type
            ),
        )
        ctx.logger = bound_logger
        event.bind_reply_handler(self._create_reply_handler(ctx, event))
        schedule_context = self._build_schedule_context(loaded, event_payload)

        # 提取 args 用于兼容 handler 签名
        raw_args = message.input.get("args") or {}
        args = dict(raw_args) if isinstance(raw_args, dict) else {}
        if not args:
            args = self._derive_args(loaded, event)

        with caller_plugin_scope(plugin_id):
            task = asyncio.create_task(
                self._run_handler(
                    loaded,
                    event,
                    ctx,
                    args,
                    schedule_context=schedule_context,
                )
            )
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
        *,
        schedule_context: ScheduleContext | None = None,
    ) -> dict[str, Any]:
        summary = {"sent_message": False, "stop": False, "call_llm": False}
        try:
            limiter = loaded.limiter
            if limiter is not None:
                decision = self._limiter.evaluate(
                    plugin_id=self._resolve_plugin_id(loaded),
                    handler_id=loaded.descriptor.id,
                    limiter=limiter,
                    event=event,
                )
                if not decision.allowed:
                    if decision.error is not None:
                        raise decision.error
                    if decision.hint:
                        await event.reply(decision.hint)
                        summary["sent_message"] = True
                    return summary
            if not self._run_local_filters(
                loaded.local_filters,
                event=event,
                ctx=ctx,
            ):
                return summary
            parsed_args, help_text = self._prepare_handler_args(
                loaded,
                args or {},
            )
            if help_text is not None:
                await event.reply(help_text)
                summary["sent_message"] = True
                return summary
            if loaded.conversation is not None:
                return await self._start_conversation(
                    loaded,
                    event,
                    ctx,
                    parsed_args,
                    schedule_context=schedule_context,
                )
            owner = loaded.owner if isinstance(loaded.owner, Star) else None
            with bind_star_runtime(owner, ctx):
                result = loaded.callable(
                    *self._build_args(
                        loaded.callable,
                        event,
                        ctx,
                        parsed_args,
                        plugin_id=self._resolve_plugin_id(loaded),
                        handler_ref=loaded.descriptor.id,
                        schedule_context=schedule_context,
                    )
                )
                if inspect.isasyncgen(result):
                    async for item in result:
                        self._merge_handler_summary(
                            summary,
                            await self._handle_result_item(item, event, ctx),
                        )
                    summary["stop"] = bool(summary.get("stop")) or event.is_stopped()
                    return summary
                if inspect.isawaitable(result):
                    result = await result
                if result is not None:
                    self._merge_handler_summary(
                        summary,
                        await self._handle_result_item(result, event, ctx),
                    )
            summary["stop"] = bool(summary.get("stop")) or event.is_stopped()
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
            param_specs = loaded.descriptor.param_specs
            for command_name in [trigger.command, *trigger.aliases]:
                remainder = self._match_command_name(event.text, command_name)
                if remainder is not None:
                    model_param = resolve_command_model_param(loaded.callable)
                    if model_param is not None:
                        return {
                            "__command_model_remainder__": remainder,
                            "__command_name__": command_name,
                        }
                    if param_specs:
                        return self._build_command_args(param_specs, remainder)
                    return self._build_command_args(
                        [
                            ParamSpec(name=name, type="str")
                            for name in self._legacy_arg_parameter_names(
                                loaded.callable
                            )
                        ],
                        remainder,
                    )
            return {}
        if isinstance(trigger, MessageTrigger) and trigger.regex:
            match = re.search(trigger.regex, event.text)
            if match is None:
                return {}
            if loaded.descriptor.param_specs:
                return self._build_regex_args(loaded.descriptor.param_specs, match)
            return self._build_regex_args(
                [
                    ParamSpec(name=name, type="str")
                    for name in self._legacy_arg_parameter_names(loaded.callable)
                ],
                match,
            )
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
        schedule_context: ScheduleContext | None = None,
        conversation_session: ConversationSession | None = None,
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
                injected = self._inject_by_type(
                    param_type,
                    event,
                    ctx,
                    schedule_context,
                    conversation_session,
                )

            # 2. Fallback 按名字注入
            if injected is None:
                if parameter.name == "event":
                    injected = event
                elif parameter.name in {"ctx", "context"}:
                    injected = ctx
                elif parameter.name in {"sched", "schedule"}:
                    injected = schedule_context
                elif parameter.name in {"conversation", "conv"}:
                    injected = conversation_session
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

    def _prepare_handler_args(
        self,
        loaded: LoadedHandler,
        args: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        parsed_args = (
            self._parse_handler_args(loaded.descriptor.param_specs, args)
            if loaded.descriptor.param_specs
            else {
                key: value
                for key, value in dict(args).items()
                if not str(key).startswith("__command_")
            }
        )
        model_param = resolve_command_model_param(loaded.callable)
        if model_param is None:
            return parsed_args, None
        if "__command_model_remainder__" not in args:
            return parsed_args, None
        trigger = loaded.descriptor.trigger
        command_name = str(args.get("__command_name__", "")) or (
            trigger.command
            if isinstance(trigger, CommandTrigger)
            else loaded.descriptor.id.rsplit(".", 1)[-1]
        )
        result = parse_command_model_remainder(
            remainder=str(args.get("__command_model_remainder__", "")),
            model_param=model_param,
            command_name=command_name,
        )
        if result.help_text is not None:
            return parsed_args, result.help_text
        if result.model is not None:
            parsed_args[model_param.name] = result.model
        return parsed_args, None

    async def _start_conversation(
        self,
        loaded: LoadedHandler,
        event: MessageEvent,
        ctx: Context,
        parsed_args: dict[str, Any],
        *,
        schedule_context: ScheduleContext | None,
    ) -> dict[str, Any]:
        assert loaded.conversation is not None
        conversation_meta = loaded.conversation
        summary = {"sent_message": False, "stop": False, "call_llm": False}
        key = f"{self._resolve_plugin_id(loaded)}:{event.session_id}"
        active = self._conversations.get(key)
        if active is not None and not active.task.done():
            if conversation_meta.mode == "reject":
                await event.reply(
                    conversation_meta.busy_message or DEFAULT_BUSY_MESSAGE
                )
                summary["sent_message"] = True
                return summary
            active.session.mark_replaced()
            await self._session_waiters.fail(
                active.session.session_key,
                ConversationReplaced("conversation replaced by a newer session"),
            )
            await asyncio.sleep(0)
            active.task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(active.task),
                    timeout=conversation_meta.grace_period,
                )
            except asyncio.TimeoutError:
                cast(PluginLogger, ctx.logger).warning(
                    "Conversation replacement grace period exceeded for handler {}",
                    loaded.descriptor.id,
                )
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            finally:
                if self._conversations.get(key) is active:
                    self._conversations.pop(key, None)

        conversation = ConversationSession(
            ctx=ctx,
            event=event,
            waiter_manager=self._session_waiters,
            timeout=conversation_meta.timeout,
        )

        async def _runner() -> None:
            try:
                await self._run_conversation_task(
                    loaded,
                    event,
                    ctx,
                    parsed_args,
                    conversation,
                    schedule_context=schedule_context,
                )
            finally:
                if conversation.state == ConversationState.ACTIVE:
                    conversation.close(ConversationState.COMPLETED)
                current = self._conversations.get(key)
                if current is not None and current.session is conversation:
                    self._conversations.pop(key, None)

        task = await ctx.register_task(
            _runner(),
            f"conversation:{loaded.descriptor.id}",
        )
        conversation.bind_owner_task(task)
        self._conversations[key] = _ActiveConversation(
            session=conversation,
            task=task,
        )
        return summary

    async def _run_conversation_task(
        self,
        loaded: LoadedHandler,
        event: MessageEvent,
        ctx: Context,
        parsed_args: dict[str, Any],
        conversation: ConversationSession,
        *,
        schedule_context: ScheduleContext | None,
    ) -> None:
        owner = loaded.owner if isinstance(loaded.owner, Star) else None
        args_with_conversation = dict(parsed_args)
        args_with_conversation.setdefault("conversation", conversation)
        try:
            with bind_star_runtime(owner, ctx):
                result = loaded.callable(
                    *self._build_args(
                        loaded.callable,
                        event,
                        ctx,
                        args_with_conversation,
                        plugin_id=self._resolve_plugin_id(loaded),
                        handler_ref=loaded.descriptor.id,
                        schedule_context=schedule_context,
                        conversation_session=conversation,
                    )
                )
                if inspect.isasyncgen(result):
                    async for item in result:
                        await self._handle_result_item(item, event, ctx)
                    return
                if inspect.isawaitable(result):
                    result = await result
                if result is not None:
                    await self._handle_result_item(result, event, ctx)
        except asyncio.CancelledError:
            if conversation.state == ConversationState.ACTIVE:
                conversation.close(ConversationState.CANCELLED)
            raise
        except (ConversationReplaced, ConversationClosed):
            return
        except Exception as exc:
            await self._handle_error(
                loaded.owner,
                exc,
                event,
                ctx,
                handler_name=loaded.callable.__name__,
                plugin_id=self._resolve_plugin_id(loaded),
            )

    def _inject_by_type(
        self,
        param_type: Any,
        event: MessageEvent,
        ctx: Context,
        schedule_context: ScheduleContext | None,
        conversation_session: ConversationSession | None,
    ) -> Any:
        """根据类型注解注入参数。"""
        param_type, _is_optional = unwrap_optional(param_type)

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
        if param_type is ScheduleContext or (
            isinstance(param_type, type) and issubclass(param_type, ScheduleContext)
        ):
            return schedule_context
        if param_type is ConversationSession or (
            isinstance(param_type, type) and issubclass(param_type, ConversationSession)
        ):
            return conversation_session

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
        if isinstance(item, MessageEventResult):
            chain = item.chain
            if chain.components:
                await event.reply_chain(chain)
                return True
            return False
        chain = coerce_message_chain(item)
        if chain is not None:
            if chain.components:
                await event.reply_chain(chain)
                return True
            return False
        if isinstance(item, list) and all(
            isinstance(component, BaseMessageComponent) for component in item
        ):
            await event.reply_chain(MessageChain(list(item)))
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
    def _build_command_args(
        cls, param_specs: Sequence[ParamSpec], remainder: str
    ) -> dict[str, Any]:
        if not param_specs or not remainder:
            return {}
        if len(param_specs) == 1:
            return {param_specs[0].name: remainder}
        parts = cls._split_command_remainder(remainder)
        values: dict[str, Any] = {}
        for index, spec in enumerate(param_specs):
            if index >= len(parts):
                break
            if spec.type == "greedy_str":
                values[spec.name] = " ".join(parts[index:])
                break
            values[spec.name] = parts[index]
        return values

    @classmethod
    def _build_regex_args(
        cls, param_specs: Sequence[ParamSpec], match: re.Match[str]
    ) -> dict[str, Any]:
        named = {
            key: value for key, value in match.groupdict().items() if value is not None
        }
        names = [spec.name for spec in param_specs if spec.name not in named]
        positional = [value for value in match.groups() if value is not None]
        for index, value in enumerate(positional):
            if index >= len(names):
                break
            named[names[index]] = value
        return named

    @staticmethod
    def _parse_handler_args(
        param_specs: Sequence[ParamSpec],
        args: dict[str, Any],
    ) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for spec in param_specs:
            if spec.name not in args:
                if spec.type == "optional":
                    parsed[spec.name] = None
                    continue
                if spec.required:
                    raise TypeError(f"缺少参数: {spec.name}")
                continue
            parsed[spec.name] = HandlerDispatcher._convert_param(spec, args[spec.name])
        return parsed

    @staticmethod
    def _convert_param(spec: ParamSpec, value: Any) -> Any:
        if spec.type in {"str", "greedy_str"}:
            return str(value)
        if spec.type == "int":
            return int(str(value))
        if spec.type == "float":
            return float(str(value))
        if spec.type == "bool":
            normalized = str(value).strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
            raise TypeError(f"无法解析布尔参数 {spec.name}: {value!r}")
        if spec.type == "optional":
            if value is None:
                return None
            inner = ParamSpec(
                name=spec.name,
                type=spec.inner_type or "str",
                required=False,
            )
            return HandlerDispatcher._convert_param(inner, value)
        return value

    @staticmethod
    def _run_local_filters(
        bindings: list[LocalFilterBinding],
        *,
        event: MessageEvent,
        ctx: Context,
    ) -> bool:
        for binding in bindings:
            if not binding.evaluate(event=event, ctx=ctx):
                return False
        return True

    @staticmethod
    def _build_schedule_context(
        loaded: LoadedHandler,
        event_payload: dict[str, Any],
    ) -> ScheduleContext | None:
        if not isinstance(loaded.descriptor.trigger, ScheduleTrigger):
            return None
        try:
            return ScheduleContext.from_payload(event_payload)
        except Exception:
            return None

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
        if name in {"event", "ctx", "context", "conversation", "conv"}:
            return True
        normalized, _is_optional = unwrap_optional(annotation)
        if normalized is None:
            return False
        if normalized in {Context, MessageEvent, ConversationSession}:
            return True
        if isinstance(normalized, type) and issubclass(
            normalized,
            (Context, MessageEvent, ConversationSession),
        ):
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
            bound_owner = owner if isinstance(owner, Star) else None
            with bind_star_runtime(bound_owner, ctx):
                result = owner.on_error(exc, event, ctx)
                if inspect.isawaitable(result):
                    await result
            return
        await Star().on_error(exc, event, ctx)


__all__ = ["CapabilityDispatcher", "HandlerDispatcher"]
