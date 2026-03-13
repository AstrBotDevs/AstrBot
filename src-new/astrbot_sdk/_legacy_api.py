"""旧版 API 的兼容实现。

这个模块承接旧 ``Context`` / ``CommandComponent`` 的运行时行为，
把仍然可映射到 v4 的能力落到 ``Context`` 客户端上，
无法等价支持的旧接口则显式给出迁移错误，而不是静默降级。
"""

from __future__ import annotations

import ast
import inspect
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from .api.basic.astrbot_config import AstrBotConfig
from .api.provider.entities import LLMResponse
from .context import Context as NewContext
from .star import Star

# TODO-迁移文档要写，我好烦烦烦你烦烦烦你
MIGRATION_DOC_URL = "https://docs.astrbot.app/migration/v3"
COMPAT_CONVERSATIONS_KEY = "__compat_conversations__"
_warned_methods: set[str] = set()


def _warn_once(old_name: str, replacement: str) -> None:
    if old_name in _warned_methods:
        return
    _warned_methods.add(old_name)
    logger.warning(
        "[AstrBot] 警告：{} 已过时。请替换为：{}\n迁移文档：{}",
        old_name,
        replacement,
        MIGRATION_DOC_URL,
    )


def _iter_registered_component_methods(
    component: Any,
) -> list[tuple[str, Callable[..., Any]]]:
    methods: list[tuple[str, Callable[..., Any]]] = []
    for attr_name, static_attr in inspect.getmembers_static(component):
        if attr_name.startswith("_") or isinstance(static_attr, property):
            continue
        if not callable(static_attr) and not isinstance(
            static_attr, (staticmethod, classmethod)
        ):
            continue
        try:
            bound_attr = getattr(component, attr_name)
        except Exception:
            continue
        if callable(bound_attr):
            methods.append((attr_name, bound_attr))
    return methods


@dataclass(slots=True)
class _CompatHookEntry:
    name: str
    priority: int
    handler: Callable[..., Any]


@dataclass(slots=True)
class _CompatToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    active: bool = True


@dataclass(slots=True)
class _CompatProviderRequest:
    prompt: str | None = None
    session_id: str | None = ""
    image_urls: list[str] | None = None
    contexts: list[dict[str, Any]] | None = None
    system_prompt: str = ""
    conversation: Any | None = None
    tool_calls_result: Any | None = None
    model: str | None = None


def _tool_parameters_from_legacy_args(
    func_args: list[dict[str, Any]],
) -> dict[str, Any]:
    parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    for item in func_args:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        if not name:
            continue
        schema = {key: value for key, value in item.items() if key != "name"}
        parameters["properties"][name] = schema
        parameters["required"].append(name)
    return parameters


class CompatLLMToolManager:
    """旧版 llm tool manager 的最小兼容实现。"""

    def __init__(self) -> None:
        self.func_list: list[_CompatToolSpec] = []

    def add_tool(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        self.remove_func(name)
        self.func_list.append(
            _CompatToolSpec(
                name=name,
                description=description,
                parameters=parameters,
                handler=handler,
            )
        )

    def add_func(
        self,
        name: str,
        func_args: list[dict[str, Any]],
        desc: str,
        handler: Callable[..., Any],
    ) -> None:
        self.add_tool(
            name=name,
            description=desc,
            parameters=_tool_parameters_from_legacy_args(func_args),
            handler=handler,
        )

    def remove_func(self, name: str) -> None:
        self.func_list = [tool for tool in self.func_list if tool.name != name]

    def get_func(self, name: str) -> _CompatToolSpec | None:
        for tool in self.func_list:
            if tool.name == name:
                return tool
        return None

    def activate_llm_tool(self, name: str) -> bool:
        tool = self.get_func(name)
        if tool is None:
            return False
        tool.active = True
        return True

    def deactivate_llm_tool(self, name: str) -> bool:
        tool = self.get_func(name)
        if tool is None:
            return False
        tool.active = False
        return True

    def get_func_desc_openai_style(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self.func_list
            if tool.active
        ]


def _legacy_tool_calls(
    response_payload: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    tool_calls = list((response_payload or {}).get("tool_calls") or [])
    tool_args: list[dict[str, Any]] = []
    tool_names: list[str] = []
    tool_ids: list[str] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function_payload = tool_call.get("function")
        if isinstance(function_payload, dict):
            name = str(function_payload.get("name") or "")
            raw_arguments = function_payload.get("arguments")
        else:
            name = str(tool_call.get("name") or "")
            raw_arguments = tool_call.get("arguments")
        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                try:
                    arguments = ast.literal_eval(raw_arguments)
                except (SyntaxError, ValueError):
                    arguments = {}
        elif isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        tool_names.append(name)
        tool_args.append(arguments)
        tool_ids.append(str(tool_call.get("id") or f"tool-{len(tool_ids) + 1}"))
    return tool_args, tool_names, tool_ids


def _legacy_llm_response(response: Any) -> LLMResponse:
    if isinstance(response, LLMResponse):
        return response

    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        payload = model_dump()
    elif isinstance(response, dict):
        payload = dict(response)
    else:
        payload = {
            "text": getattr(response, "text", ""),
            "usage": getattr(response, "usage", None),
            "finish_reason": getattr(response, "finish_reason", None),
            "tool_calls": getattr(response, "tool_calls", []),
        }

    tool_args, tool_names, tool_ids = _legacy_tool_calls(payload)
    return LLMResponse(
        role=str(payload.get("role") or "assistant"),
        completion_text=str(payload.get("text") or ""),
        tools_call_args=tool_args,
        tools_call_name=tool_names,
        tools_call_ids=tool_ids,
        raw_completion=response,
        _new_record=payload,
    )


class LegacyConversationManager:
    """旧版会话管理器的兼容实现。

    会话数据通过 ``ctx.db`` 存在统一 key 下。
    数据是否持久化取决于当前 db capability 的后端实现，而不是 compat 层本身。
    """

    __compat_component_name__ = "ConversationManager"

    def __init__(self, parent: "LegacyContext") -> None:
        self._parent = parent
        self._counters: defaultdict[str, int] = defaultdict(int)
        # 记录每个 unified_msg_origin 的当前会话 ID
        self._current_conversations: dict[str, str] = {}

    def _ctx(self) -> NewContext:
        return self._parent.require_runtime_context()

    async def _get_stored(self) -> dict[str, dict[str, Any]]:
        """获取存储的所有会话数据。"""
        ctx = self._ctx()
        stored = await ctx.db.get(COMPAT_CONVERSATIONS_KEY)
        return stored if isinstance(stored, dict) else {}

    async def _set_stored(self, stored: dict[str, dict[str, Any]]) -> None:
        """保存会话数据。"""
        ctx = self._ctx()
        await ctx.db.set(COMPAT_CONVERSATIONS_KEY, stored)

    async def new_conversation(
        self,
        unified_msg_origin: str,
        platform_id: str | None = None,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> str:
        """创建新会话并返回会话 ID。"""
        ctx = self._ctx()
        stored = await self._get_stored()
        next_counter = self._counters[unified_msg_origin]
        while True:
            next_counter += 1
            conversation_id = f"{ctx.plugin_id}-conv-{next_counter}"
            if conversation_id not in stored:
                break
        self._counters[unified_msg_origin] = next_counter
        stored[conversation_id] = {
            "unified_msg_origin": unified_msg_origin,
            "platform_id": platform_id,
            "content": content or [],
            "title": title,
            "persona_id": persona_id,
        }
        await self._set_stored(stored)
        # 设置为当前会话
        self._current_conversations[unified_msg_origin] = conversation_id
        return conversation_id

    async def switch_conversation(
        self, unified_msg_origin: str, conversation_id: str
    ) -> None:
        """切换到指定会话。

        Args:
            unified_msg_origin: 统一消息来源
            conversation_id: 要切换到的会话 ID
        """
        stored = await self._get_stored()
        if conversation_id not in stored:
            return
        # 验证会话属于该 unified_msg_origin
        conv_data = stored[conversation_id]
        if conv_data.get("unified_msg_origin") != unified_msg_origin:
            return
        self._current_conversations[unified_msg_origin] = conversation_id

    async def delete_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str | None = None,
    ) -> None:
        """删除指定会话。

        当 conversation_id 为 None 时，删除当前会话。

        Args:
            unified_msg_origin: 统一消息来源
            conversation_id: 要删除的会话 ID，为 None 时删除当前会话
        """
        # 如果 conversation_id 为 None，使用当前会话
        if conversation_id is None:
            conversation_id = self._current_conversations.get(unified_msg_origin)
            if conversation_id is None:
                return

        stored = await self._get_stored()
        if conversation_id not in stored:
            return
        conv_data = stored[conversation_id]
        if conv_data.get("unified_msg_origin") != unified_msg_origin:
            return
        del stored[conversation_id]
        await self._set_stored(stored)
        # 如果删除的是当前会话，清除当前会话记录
        if self._current_conversations.get(unified_msg_origin) == conversation_id:
            del self._current_conversations[unified_msg_origin]

    async def get_curr_conversation_id(self, unified_msg_origin: str) -> str | None:
        """获取当前会话 ID。

        Args:
            unified_msg_origin: 统一消息来源

        Returns:
            当前会话 ID，若无则返回 None
        """
        return self._current_conversations.get(unified_msg_origin)

    async def get_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str,
        create_if_not_exists: bool = False,
    ) -> dict[str, Any] | None:
        """获取指定会话的数据。

        Args:
            unified_msg_origin: 统一消息来源
            conversation_id: 会话 ID
            create_if_not_exists: 如果会话不存在，是否创建新会话

        Returns:
            会话数据字典，不存在则返回 None
        """
        stored = await self._get_stored()
        conv = stored.get(conversation_id)
        if conv is None and create_if_not_exists:
            # 创建新会话
            conv = {
                "unified_msg_origin": unified_msg_origin,
                "platform_id": None,
                "content": [],
                "title": None,
                "persona_id": None,
            }
            stored[conversation_id] = conv
            await self._set_stored(stored)
            self._current_conversations[unified_msg_origin] = conversation_id
        return conv

    async def get_conversations(
        self,
        unified_msg_origin: str | None = None,
        platform_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取会话列表。

        Args:
            unified_msg_origin: 统一消息来源，可选
            platform_id: 平台 ID，可选

        Returns:
            会话列表，每个元素包含 conversation_id 和会话数据
        """
        stored = await self._get_stored()
        result = []
        for conv_id, conv_data in stored.items():
            # 按 unified_msg_origin 过滤
            if unified_msg_origin is not None:
                if conv_data.get("unified_msg_origin") != unified_msg_origin:
                    continue
            # 按 platform_id 过滤
            if platform_id is not None:
                if conv_data.get("platform_id") != platform_id:
                    continue
            result.append({"conversation_id": conv_id, **conv_data})
        return result

    async def update_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str | None = None,
        history: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> None:
        """更新会话数据。

        Args:
            unified_msg_origin: 统一消息来源
            conversation_id: 会话 ID，为 None 时更新当前会话
            history: 对话历史记录
            title: 会话标题
            persona_id: Persona ID
        """
        # 如果 conversation_id 为 None，使用当前会话
        if conversation_id is None:
            conversation_id = self._current_conversations.get(unified_msg_origin)
            if conversation_id is None:
                return

        stored = await self._get_stored()
        if conversation_id not in stored:
            return

        updates: dict[str, Any] = {}
        if history is not None:
            updates["content"] = history
        if title is not None:
            updates["title"] = title
        if persona_id is not None:
            updates["persona_id"] = persona_id

        stored[conversation_id].update(updates)
        await self._set_stored(stored)

    async def delete_conversations_by_user_id(self, unified_msg_origin: str) -> None:
        """删除指定用户的所有会话。

        Args:
            unified_msg_origin: 统一消息来源
        """
        stored = await self._get_stored()
        to_delete = [
            conv_id
            for conv_id, conv_data in stored.items()
            if conv_data.get("unified_msg_origin") == unified_msg_origin
        ]
        for conv_id in to_delete:
            del stored[conv_id]
        await self._set_stored(stored)
        # 清除当前会话记录
        if unified_msg_origin in self._current_conversations:
            del self._current_conversations[unified_msg_origin]

    async def add_message_pair(
        self,
        cid: str,
        user_message: str | dict,
        assistant_message: str | dict,
    ) -> None:
        """向会话添加消息对。

        Args:
            cid: 会话 ID
            user_message: 用户消息
            assistant_message: 助手消息
        """
        stored = await self._get_stored()
        if cid not in stored:
            return
        content = stored[cid].get("content", [])
        # 处理消息格式
        user_msg = (
            user_message
            if isinstance(user_message, dict)
            else {"role": "user", "content": user_message}
        )
        assistant_msg = (
            assistant_message
            if isinstance(assistant_message, dict)
            else {"role": "assistant", "content": assistant_message}
        )
        content.append(user_msg)
        content.append(assistant_msg)
        stored[cid]["content"] = content
        await self._set_stored(stored)

    async def update_conversation_title(
        self,
        unified_msg_origin: str,
        title: str,
        conversation_id: str | None = None,
    ) -> None:
        """更新会话标题。

        Args:
            unified_msg_origin: 统一消息来源
            title: 会话标题
            conversation_id: 会话 ID，为 None 时更新当前会话

        Deprecated:
            请使用 update_conversation() 的 title 参数。
        """
        await self.update_conversation(unified_msg_origin, conversation_id, title=title)

    async def update_conversation_persona_id(
        self,
        unified_msg_origin: str,
        persona_id: str,
        conversation_id: str | None = None,
    ) -> None:
        """更新会话 Persona ID。

        Args:
            unified_msg_origin: 统一消息来源
            persona_id: Persona ID
            conversation_id: 会话 ID，为 None 时更新当前会话

        Deprecated:
            请使用 update_conversation() 的 persona_id 参数。
        """
        await self.update_conversation(
            unified_msg_origin, conversation_id, persona_id=persona_id
        )

    async def get_filtered_conversations(self, *args: Any, **kwargs: Any) -> Any:
        """兼容旧版会话过滤接口。"""
        unified_msg_origin = kwargs.get("unified_msg_origin")
        platform_id = kwargs.get("platform_id")
        keyword = kwargs.get("keyword") or kwargs.get("query")
        conversations = await self.get_conversations(
            unified_msg_origin=unified_msg_origin,
            platform_id=platform_id,
        )
        if not isinstance(keyword, str) or not keyword:
            return conversations
        filtered: list[dict[str, Any]] = []
        for conversation in conversations:
            haystack = json.dumps(conversation, ensure_ascii=False)
            if keyword in haystack:
                filtered.append(conversation)
        return filtered

    async def get_human_readable_context(self, *args: Any, **kwargs: Any) -> Any:
        """把兼容会话内容格式化为可读文本。"""
        unified_msg_origin = kwargs.get("unified_msg_origin")
        conversation_id = kwargs.get("conversation_id")
        if conversation_id is None and isinstance(unified_msg_origin, str):
            conversation_id = await self.get_curr_conversation_id(unified_msg_origin)
        if not isinstance(conversation_id, str) or not conversation_id:
            return ""
        conversation = await self.get_conversation(
            unified_msg_origin or "",
            conversation_id,
            create_if_not_exists=False,
        )
        if not isinstance(conversation, dict):
            return ""
        lines: list[str] = []
        for item in conversation.get("content", []):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "unknown")
            content = item.get("content")
            if isinstance(content, list):
                rendered = json.dumps(content, ensure_ascii=False)
            else:
                rendered = str(content or "")
            lines.append(f"{role}: {rendered}".rstrip())
        return "\n".join(lines)


class LegacyContext:
    """旧版 ``Context`` 的兼容外观。"""

    def __init__(self, plugin_id: str) -> None:
        self.plugin_id = plugin_id
        self._runtime_context: NewContext | None = None
        self._registered_managers: dict[str, Any] = {}
        self._registered_functions: dict[str, Callable[..., Any]] = {}
        self._compat_hooks: defaultdict[str, list[_CompatHookEntry]] = defaultdict(list)
        self._llm_tools = CompatLLMToolManager()
        self.conversation_manager = LegacyConversationManager(self)
        self._register_component(self.conversation_manager)

    def bind_runtime_context(self, runtime_context: NewContext) -> None:
        self._runtime_context = runtime_context

    def require_runtime_context(self) -> NewContext:
        if self._runtime_context is None:
            raise RuntimeError("LegacyContext 尚未绑定运行时 Context")
        return self._runtime_context

    def get_llm_tool_manager(self) -> CompatLLMToolManager:
        return self._llm_tools

    def activate_llm_tool(self, name: str) -> bool:
        return self._llm_tools.activate_llm_tool(name)

    def deactivate_llm_tool(self, name: str) -> bool:
        return self._llm_tools.deactivate_llm_tool(name)

    def register_llm_tool(
        self,
        name: str,
        func_args: list[dict[str, Any]],
        desc: str,
        func_obj: Callable[..., Any],
    ) -> None:
        self._llm_tools.add_func(name, func_args, desc, func_obj)

    def unregister_llm_tool(self, name: str) -> None:
        self._llm_tools.remove_func(name)

    def get_config(self) -> dict[str, Any]:
        runtime_context = self._runtime_context
        if runtime_context is None:
            return {}
        config = getattr(runtime_context, "_astrbot_config", None)
        return dict(config) if isinstance(config, dict) else {}

    def _runtime_config(self) -> Any:
        runtime_context = self._runtime_context
        config = (
            getattr(runtime_context, "_astrbot_config", None)
            if runtime_context
            else None
        )
        if isinstance(config, AstrBotConfig):
            return config
        if isinstance(config, dict):
            return AstrBotConfig(dict(config))
        return AstrBotConfig({})

    @staticmethod
    def _merge_llm_kwargs(
        *,
        chat_provider_id: str,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(kwargs)
        if chat_provider_id:
            merged.setdefault("provider_id", chat_provider_id)
        return merged

    @staticmethod
    def _apply_request_overrides(
        call_kwargs: dict[str, Any],
        request: _CompatProviderRequest,
    ) -> dict[str, Any]:
        updated = dict(call_kwargs)
        if request.model:
            updated["model"] = request.model
        return updated

    @staticmethod
    def _component_names(component: Any) -> list[str]:
        names = [component.__class__.__name__]
        compat_name = getattr(component, "__compat_component_name__", None)
        if isinstance(compat_name, str) and compat_name and compat_name not in names:
            names.insert(0, compat_name)
        return names

    def _register_hook(
        self,
        name: str,
        handler: Callable[..., Any],
        *,
        priority: int = 0,
    ) -> None:
        self._compat_hooks[name].append(
            _CompatHookEntry(name=name, priority=priority, handler=handler)
        )
        self._compat_hooks[name].sort(key=lambda item: item.priority, reverse=True)

    def _register_compat_component(self, component: Any) -> None:
        from .api.event.filter import (
            get_compat_hook_metas,
            get_compat_llm_tool_meta,
        )

        for _attr_name, attr in _iter_registered_component_methods(component):
            tool_meta = get_compat_llm_tool_meta(attr)
            if tool_meta is not None:
                self._llm_tools.add_tool(
                    name=tool_meta.name,
                    description=tool_meta.description,
                    parameters=_tool_parameters_from_legacy_args(tool_meta.parameters),
                    handler=attr,
                )
            for hook_meta in get_compat_hook_metas(attr):
                self._register_hook(
                    hook_meta.name,
                    attr,
                    priority=hook_meta.priority,
                )

    @staticmethod
    def _legacy_event(event: Any | None):
        if event is None:
            return None
        from .api.event import AstrMessageEvent

        if isinstance(event, AstrMessageEvent):
            return event
        return AstrMessageEvent.from_message_event(event)

    @staticmethod
    def _hook_type_injection(
        annotation: Any,
        available: dict[str, Any],
    ) -> Any:
        from .api.event import AstrMessageEvent
        from .context import Context as RuntimeContext

        if annotation is Any or annotation is inspect.Signature.empty:
            return None
        if annotation is AstrMessageEvent:
            return available.get("event")
        if annotation is RuntimeContext or annotation is NewContext:
            return available.get("context")
        if annotation is LegacyContext:
            return available.get("legacy_context")
        if annotation is LLMResponse:
            return available.get("response")
        return None

    async def _call_with_available(
        self,
        handler: Callable[..., Any],
        available: dict[str, Any],
    ) -> Any:
        signature = inspect.signature(handler)
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        for parameter in signature.parameters.values():
            injected = None
            if parameter.name in available:
                injected = available[parameter.name]
            else:
                injected = self._hook_type_injection(parameter.annotation, available)
            if injected is None:
                if parameter.default is not parameter.empty:
                    continue
                continue
            if parameter.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                args.append(injected)
            elif parameter.kind == inspect.Parameter.KEYWORD_ONLY:
                kwargs[parameter.name] = injected
        result = handler(*args, **kwargs)
        if inspect.isasyncgen(result):
            final_value = None
            async for item in result:
                final_value = item
                await self._consume_tool_result(
                    available.get("event"),
                    available.get("context"),
                    item,
                )
            return final_value
        if inspect.isawaitable(result):
            return await result
        return result

    async def _run_compat_hook(
        self,
        name: str,
        **available: Any,
    ) -> list[Any]:
        hook_results: list[Any] = []
        for entry in self._compat_hooks.get(name, []):
            hook_results.append(
                await self._call_with_available(entry.handler, available)
            )
        return hook_results

    async def _consume_tool_result(
        self,
        event: Any | None,
        runtime_context: NewContext | None,
        item: Any,
    ) -> None:
        if event is None:
            return
        from .api.event.event_result import MessageEventResult
        from .api.message.chain import MessageChain

        legacy_event = self._legacy_event(event)
        if legacy_event is None:
            return
        if isinstance(item, MessageEventResult):
            if (
                item.chain
                and runtime_context is not None
                and not item.is_plain_text_only()
            ):
                await runtime_context.platform.send_chain(
                    legacy_event.session_ref or legacy_event.session_id,
                    item.to_payload(),
                )
                return
            plain_text = item.get_plain_text()
            if plain_text:
                await legacy_event.reply(plain_text)
            return
        if isinstance(item, MessageChain):
            if (
                item.chain
                and runtime_context is not None
                and not item.is_plain_text_only()
            ):
                await runtime_context.platform.send_chain(
                    legacy_event.session_ref or legacy_event.session_id,
                    item.to_payload(),
                )
                return
            plain_text = item.get_plain_text()
            if plain_text:
                await legacy_event.reply(plain_text)
            return
        if isinstance(item, str):
            await legacy_event.reply(item)

    async def _invoke_llm_tool(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        event: Any | None,
    ) -> str:
        tool = self._llm_tools.get_func(tool_name)
        if tool is None or not tool.active:
            return f"tool '{tool_name}' not found"
        legacy_event = self._legacy_event(event)
        runtime_context = self.require_runtime_context()
        await self._run_compat_hook(
            "on_using_llm_tool",
            event=legacy_event,
            context=runtime_context,
            legacy_context=self,
            tool=tool,
            tool_args=tool_args,
        )
        tool_result = await self._call_with_available(
            tool.handler,
            {
                **tool_args,
                "event": legacy_event,
                "context": runtime_context,
                "ctx": runtime_context,
                "legacy_context": self,
            },
        )
        if isinstance(tool_result, str):
            normalized = tool_result
        elif tool_result is None:
            normalized = ""
        else:
            normalized = str(tool_result)
        await self._run_compat_hook(
            "on_llm_tool_respond",
            event=legacy_event,
            context=runtime_context,
            legacy_context=self,
            tool=tool,
            tool_args=tool_args,
            tool_result=normalized,
        )
        return normalized

    def _register_component(self, *components: Any) -> None:
        """保留旧版按名称暴露组件方法的兼容链路。"""
        for component in components:
            for class_name in self._component_names(component):
                self._registered_managers[class_name] = component
                for attr_name, attr in _iter_registered_component_methods(component):
                    self._registered_functions[f"{class_name}.{attr_name}"] = attr
            self._register_compat_component(component)

    async def execute_registered_function(
        self,
        func_full_name: str,
        args: dict[str, Any] | None = None,
    ) -> Any:
        if args is None:
            call_args: dict[str, Any] = {}
        elif isinstance(args, dict):
            call_args = args
        else:
            raise TypeError("LegacyContext 调用参数必须是 dict")

        func = self._registered_functions.get(func_full_name)
        if func is None:
            raise ValueError(f"Function not found: {func_full_name}")

        result = func(**call_args)
        if inspect.isawaitable(result):
            return await result
        return result

    async def call_context_function(
        self,
        func_full_name: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "data": await self.execute_registered_function(func_full_name, args),
        }

    async def llm_generate(
        self,
        chat_provider_id: str,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
        tools: Any | None = None,
        system_prompt: str | None = None,
        contexts: list[dict] | None = None,
        event: Any | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        _warn_once("context.llm_generate()", "ctx.llm.chat_raw(...)")
        ctx = self.require_runtime_context()
        call_kwargs = self._merge_llm_kwargs(
            chat_provider_id=chat_provider_id,
            kwargs=kwargs,
        )
        legacy_event = self._legacy_event(event)
        request = _CompatProviderRequest(
            prompt=prompt or "",
            session_id=legacy_event.session_id if legacy_event is not None else "",
            image_urls=list(image_urls or []),
            contexts=list(contexts or []),
            system_prompt=system_prompt or "",
            model=call_kwargs.get("model"),
        )
        await self._run_compat_hook(
            "on_waiting_llm_request",
            event=legacy_event,
            context=ctx,
            legacy_context=self,
        )
        await self._run_compat_hook(
            "on_llm_request",
            event=legacy_event,
            context=ctx,
            legacy_context=self,
            request=request,
        )
        call_kwargs = self._apply_request_overrides(call_kwargs, request)
        response = await ctx.llm.chat_raw(
            request.prompt or "",
            system=request.system_prompt or None,
            history=request.contexts or [],
            image_urls=request.image_urls or [],
            tools=tools,
            **call_kwargs,
        )
        legacy_response = _legacy_llm_response(response)
        await self._run_compat_hook(
            "on_llm_response",
            event=legacy_event,
            context=ctx,
            legacy_context=self,
            response=legacy_response,
        )
        return legacy_response

    async def tool_loop_agent(
        self,
        chat_provider_id: str,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
        tools: Any | None = None,
        system_prompt: str | None = None,
        contexts: list[dict] | None = None,
        max_steps: int = 30,
        event: Any | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        _warn_once("context.tool_loop_agent()", "compat local tool loop")
        ctx = self.require_runtime_context()
        call_kwargs = self._merge_llm_kwargs(
            chat_provider_id=chat_provider_id,
            kwargs=kwargs,
        )
        legacy_event = self._legacy_event(event)
        history = list(contexts or [])
        request_prompt = prompt or ""
        combined_tools = list(self._llm_tools.get_func_desc_openai_style())
        if isinstance(tools, list):
            combined_tools.extend(item for item in tools if isinstance(item, dict))
        elif tools is not None:
            openai_schema = getattr(tools, "openai_schema", None)
            if callable(openai_schema):
                extra_tools = openai_schema()
                if isinstance(extra_tools, list):
                    combined_tools.extend(
                        item for item in extra_tools if isinstance(item, dict)
                    )

        final_response = LLMResponse(role="assistant")
        for _step in range(max_steps):
            request = _CompatProviderRequest(
                prompt=request_prompt,
                session_id=legacy_event.session_id if legacy_event is not None else "",
                image_urls=list(image_urls or []),
                contexts=list(history),
                system_prompt=system_prompt or "",
                model=call_kwargs.get("model"),
            )
            await self._run_compat_hook(
                "on_waiting_llm_request",
                event=legacy_event,
                context=ctx,
                legacy_context=self,
            )
            await self._run_compat_hook(
                "on_llm_request",
                event=legacy_event,
                context=ctx,
                legacy_context=self,
                request=request,
            )
            call_kwargs = self._apply_request_overrides(call_kwargs, request)
            response = await ctx.llm.chat_raw(
                request.prompt or "",
                system=request.system_prompt or None,
                history=request.contexts or [],
                image_urls=request.image_urls or [],
                tools=combined_tools or None,
                max_steps=max_steps,
                **call_kwargs,
            )
            final_response = _legacy_llm_response(response)
            await self._run_compat_hook(
                "on_llm_response",
                event=legacy_event,
                context=ctx,
                legacy_context=self,
                response=final_response,
            )
            if not final_response.tools_call_name:
                return final_response

            history.append(
                {
                    "role": "assistant",
                    "content": final_response.completion_text,
                    "tool_calls": final_response.to_openai_tool_calls(),
                }
            )
            for tool_name, tool_args, tool_call_id in zip(
                final_response.tools_call_name,
                final_response.tools_call_args,
                final_response.tools_call_ids,
                strict=False,
            ):
                tool_result = await self._invoke_llm_tool(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    event=legacy_event,
                )
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": tool_name,
                        "content": tool_result,
                    }
                )
            request_prompt = ""

        return final_response

    async def send_message(self, session: str, message_chain: Any) -> None:
        _warn_once(
            "context.send_message()",
            "ctx.platform.send(...) / ctx.platform.send_chain(...)",
        )
        ctx = self.require_runtime_context()
        chain = getattr(message_chain, "chain", None)
        to_payload = getattr(message_chain, "to_payload", None)
        is_plain_text_only = getattr(message_chain, "is_plain_text_only", None)
        if (
            isinstance(chain, list)
            and callable(to_payload)
            and not (callable(is_plain_text_only) and is_plain_text_only())
        ):
            await ctx.platform.send_chain(session, to_payload())
            return

        # 旧版插件也可能传纯文本对象，compat 层保留文本兜底。
        if hasattr(message_chain, "get_plain_text") and callable(
            message_chain.get_plain_text
        ):
            text = message_chain.get_plain_text()
        elif hasattr(message_chain, "to_text") and callable(message_chain.to_text):
            text = message_chain.to_text()
        else:
            text = str(message_chain)
        await ctx.platform.send(session, text)

    async def add_llm_tools(self, *tools: Any) -> None:
        for tool in tools:
            name = getattr(tool, "name", None)
            if not isinstance(name, str) or not name:
                raise TypeError("add_llm_tools() 需要带 name 的工具对象")
            handler = getattr(tool, "handler", None)
            if not callable(handler):
                raise TypeError("add_llm_tools() 需要工具对象提供可调用的 handler")
            parameters = getattr(tool, "parameters", None)
            if not isinstance(parameters, dict):
                func_args = getattr(tool, "func_args", None)
                if isinstance(func_args, list):
                    parameters = _tool_parameters_from_legacy_args(func_args)
                else:
                    parameters = {"type": "object", "properties": {}, "required": []}
            description = str(getattr(tool, "description", "") or "")
            self._llm_tools.add_tool(
                name=name,
                description=description,
                parameters=parameters,
                handler=handler,
            )

    async def put_kv_data(self, key: str, value: Any) -> None:
        _warn_once("context.put_kv_data()", "ctx.db.set(key, value)")
        ctx = self.require_runtime_context()
        await ctx.db.set(key, value)

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        _warn_once("context.get_kv_data()", "ctx.db.get(key)")
        ctx = self.require_runtime_context()
        value = await ctx.db.get(key)
        return default if value is None else value

    async def delete_kv_data(self, key: str) -> None:
        _warn_once("context.delete_kv_data()", "ctx.db.delete(key)")
        ctx = self.require_runtime_context()
        await ctx.db.delete(key)


class StarTools:
    """旧版 ``StarTools`` 的最小兼容实现。"""

    @staticmethod
    def get_data_dir() -> Path:
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        try:
            while caller is not None:
                caller_file = caller.f_globals.get("__file__")
                if isinstance(caller_file, str) and caller_file:
                    data_dir = Path(caller_file).resolve().parent / "data"
                    data_dir.mkdir(parents=True, exist_ok=True)
                    return data_dir
                caller = caller.f_back
        finally:
            del frame
        data_dir = Path.cwd() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir


class LegacyStar(Star):
    """旧版 ``astrbot.api.star.Star`` 兼容基类。"""

    def __init__(self, context: LegacyContext | None = None, config: Any | None = None):
        self.context = context
        if config is not None:
            self.config = config

    def _require_legacy_context(self) -> LegacyContext:
        if self.context is None:
            raise RuntimeError("LegacyStar 尚未绑定 compat Context")
        return self.context

    async def put_kv_data(self, key: str, value: Any) -> None:
        await self._require_legacy_context().put_kv_data(key, value)

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        return await self._require_legacy_context().get_kv_data(key, default)

    async def delete_kv_data(self, key: str) -> None:
        await self._require_legacy_context().delete_kv_data(key)

    async def send_message(self, session: str, message_chain: Any) -> None:
        await self._require_legacy_context().send_message(session, message_chain)

    async def llm_generate(
        self,
        chat_provider_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return await self._require_legacy_context().llm_generate(
            chat_provider_id,
            *args,
            **kwargs,
        )

    async def tool_loop_agent(
        self,
        chat_provider_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return await self._require_legacy_context().tool_loop_agent(
            chat_provider_id,
            *args,
            **kwargs,
        )

    async def add_llm_tools(self, *tools: Any) -> None:
        await self._require_legacy_context().add_llm_tools(*tools)

    def get_llm_tool_manager(self) -> CompatLLMToolManager:
        return self._require_legacy_context().get_llm_tool_manager()

    def activate_llm_tool(self, name: str) -> bool:
        return self._require_legacy_context().activate_llm_tool(name)

    def deactivate_llm_tool(self, name: str) -> bool:
        return self._require_legacy_context().deactivate_llm_tool(name)

    def register_llm_tool(
        self,
        name: str,
        func_args: list[dict[str, Any]],
        desc: str,
        func_obj: Callable[..., Any],
    ) -> None:
        self._require_legacy_context().register_llm_tool(
            name,
            func_args,
            desc,
            func_obj,
        )

    def unregister_llm_tool(self, name: str) -> None:
        self._require_legacy_context().unregister_llm_tool(name)

    def get_config(self) -> dict[str, Any]:
        return self._require_legacy_context().get_config()

    @classmethod
    def __astrbot_is_new_star__(cls) -> bool:
        return False

    @classmethod
    def _astrbot_create_legacy_context(cls, plugin_id: str) -> LegacyContext:
        return LegacyContext(plugin_id)


class CommandComponent(LegacyStar):
    @classmethod
    def __astrbot_is_new_star__(cls) -> bool:
        return False

    @classmethod
    def _astrbot_create_legacy_context(cls, plugin_id: str) -> LegacyContext:
        # Loader 通过这个工厂拿到旧 Context，避免核心运行时直接依赖 compat 实现。
        return LegacyContext(plugin_id)


def register(
    name: str | None = None,
    author: str | None = None,
    desc: str | None = None,
    version: str | None = None,
    repo: str | None = None,
):
    """旧版插件元数据装饰器兼容入口。"""

    metadata = {
        "name": name,
        "author": author,
        "desc": desc,
        "version": version,
        "repo": repo,
    }

    def decorator(cls):
        existing = getattr(cls, "__astrbot_plugin_metadata__", {})
        setattr(
            cls,
            "__astrbot_plugin_metadata__",
            {
                **existing,
                **{key: value for key, value in metadata.items() if value is not None},
            },
        )
        return cls

    return decorator


Context = LegacyContext

__all__ = [
    "CommandComponent",
    "Context",
    "LegacyContext",
    "LegacyConversationManager",
    "LegacyStar",
    "MIGRATION_DOC_URL",
    "StarTools",
    "register",
]
