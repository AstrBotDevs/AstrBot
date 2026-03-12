from __future__ import annotations

from collections import defaultdict
from typing import Any

from loguru import logger

from .clients.llm import LLMResponse
from .context import Context as NewContext

MIGRATION_DOC_URL = "https://docs.astrbot.app/migration/v3"
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


class LegacyConversationManager:
    def __init__(self, parent: "LegacyContext") -> None:
        self._parent = parent
        self._counters: defaultdict[str, int] = defaultdict(int)

    def _ctx(self) -> NewContext:
        return self._parent.require_runtime_context()

    async def new_conversation(
        self,
        unified_msg_origin: str,
        platform_id: str | None = None,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> str:
        ctx = self._ctx()
        self._counters[unified_msg_origin] += 1
        conversation_id = f"{ctx.plugin_id}-conv-{self._counters[unified_msg_origin]}"
        stored = await ctx.db.get("__compat_conversations__") or {}
        stored[conversation_id] = {
            "unified_msg_origin": unified_msg_origin,
            "platform_id": platform_id,
            "content": content or [],
            "title": title,
            "persona_id": persona_id,
        }
        await ctx.db.set("__compat_conversations__", stored)
        return conversation_id


class LegacyContext:
    def __init__(self, plugin_id: str) -> None:
        self.plugin_id = plugin_id
        self._runtime_context: NewContext | None = None
        self.conversation_manager = LegacyConversationManager(self)

    def bind_runtime_context(self, runtime_context: NewContext) -> None:
        self._runtime_context = runtime_context

    def require_runtime_context(self) -> NewContext:
        if self._runtime_context is None:
            raise RuntimeError("LegacyContext 尚未绑定运行时 Context")
        return self._runtime_context

    async def llm_generate(
        self,
        chat_provider_id: str,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
        tools: Any | None = None,
        system_prompt: str | None = None,
        contexts: list[dict] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        _warn_once("context.llm_generate()", "ctx.llm.chat(prompt)")
        ctx = self.require_runtime_context()
        return await ctx.llm.chat_raw(
            prompt or "",
            system=system_prompt,
            history=contexts or [],
            image_urls=image_urls or [],
            tools=tools,
            **kwargs,
        )

    async def tool_loop_agent(
        self,
        chat_provider_id: str,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
        tools: Any | None = None,
        system_prompt: str | None = None,
        contexts: list[dict] | None = None,
        max_steps: int = 30,
        **kwargs: Any,
    ) -> LLMResponse:
        _warn_once("context.tool_loop_agent()", "ctx.llm.chat_raw(...)")
        ctx = self.require_runtime_context()
        return await ctx.llm.chat_raw(
            prompt or "",
            system=system_prompt,
            history=contexts or [],
            image_urls=image_urls or [],
            tools=tools,
            max_steps=max_steps,
            **kwargs,
        )

    async def send_message(self, session: str, message_chain: Any) -> None:
        _warn_once("context.send_message()", "ctx.platform.send(session, text)")
        ctx = self.require_runtime_context()
        await ctx.platform.send(session, str(message_chain))

    async def add_llm_tools(self, *tools: Any) -> None:
        _warn_once("context.add_llm_tools()", "ctx.llm.chat_raw(..., tools=...)")
        return None

    async def put_kv_data(self, key: str, value: dict[str, Any]) -> None:
        _warn_once("context.put_kv_data()", "ctx.db.set(key, value)")
        ctx = self.require_runtime_context()
        await ctx.db.set(key, value)

    async def get_kv_data(self, key: str) -> dict[str, Any] | None:
        _warn_once("context.get_kv_data()", "ctx.db.get(key)")
        ctx = self.require_runtime_context()
        return await ctx.db.get(key)

    async def delete_kv_data(self, key: str) -> None:
        _warn_once("context.delete_kv_data()", "ctx.db.delete(key)")
        ctx = self.require_runtime_context()
        await ctx.db.delete(key)


class CommandComponent:
    @classmethod
    def _astrbot_create_legacy_context(cls, plugin_id: str) -> LegacyContext:
        # Loader 通过这个工厂拿到旧 Context，避免核心运行时直接依赖 compat 实现。
        return LegacyContext(plugin_id)


Context = LegacyContext

__all__ = [
    "CommandComponent",
    "Context",
    "LegacyContext",
    "LegacyConversationManager",
    "MIGRATION_DOC_URL",
]
