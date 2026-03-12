from __future__ import annotations

from collections import defaultdict
from typing import Any

from loguru import logger

from .clients.llm import LLMResponse
from .context import Context as NewContext
from .star import Star

# TODO-迁移文档要写，我好烦烦烦你烦烦烦你
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
    """旧版会话管理器的兼容实现。

    使用 db 存储会话数据，key 为 `__compat_conversations__`。

    注意：此实现不提供持久化保证，会话数据仅在当前运行时有效。
    """

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
        stored = await ctx.db.get("__compat_conversations__")
        return stored if isinstance(stored, dict) else {}

    async def _set_stored(self, stored: dict[str, dict[str, Any]]) -> None:
        """保存会话数据。"""
        ctx = self._ctx()
        await ctx.db.set("__compat_conversations__", stored)

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
        self._counters[unified_msg_origin] += 1
        conversation_id = f"{ctx.plugin_id}-conv-{self._counters[unified_msg_origin]}"
        stored = await self._get_stored()
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
        await self.update_conversation(
            unified_msg_origin, conversation_id, title=title
        )

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
        """已弃用：v4 不支持此方法。"""
        raise NotImplementedError(
            "get_filtered_conversations() 在 v4 中不再支持。\n"
            f"请使用 ctx.db.query(...) 自行实现过滤逻辑。\n"
            f"迁移文档：{MIGRATION_DOC_URL}"
        )

    async def get_human_readable_context(self, *args: Any, **kwargs: Any) -> Any:
        """已弃用：v4 不支持此方法。"""
        raise NotImplementedError(
            "get_human_readable_context() 在 v4 中不再支持。\n"
            f"请自行遍历会话 content 字段格式化输出。\n"
            f"迁移文档：{MIGRATION_DOC_URL}"
        )


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
        _warn_once("context.llm_generate()", "ctx.llm.chat_raw(...)")
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
        # 正确序列化 MessageChain 对象
        # 优先使用 get_plain_text() 方法（旧版 MessageChain）
        if hasattr(message_chain, "get_plain_text") and callable(
            message_chain.get_plain_text
        ):
            text = message_chain.get_plain_text()
        elif hasattr(message_chain, "to_text") and callable(message_chain.to_text):
            text = message_chain.to_text()
        else:
            text = str(message_chain)
        await ctx.platform.send(session, text)

    # TODO:迁移文档中说明已废弃 add_llm_tools()，但仍保留接口以避免核心依赖问题。后续版本将移除此接口。
    async def add_llm_tools(self, *tools: Any) -> None:
        raise NotImplementedError(
            "context.add_llm_tools() 在 v4 中不再支持。\n"
            "请使用 ctx.llm.chat_raw(..., tools=[...]) 直接传递工具。\n"
            f"迁移文档：{MIGRATION_DOC_URL}"
        )

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


class CommandComponent(Star):
    @classmethod
    def __astrbot_is_new_star__(cls) -> bool:
        return False

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
