"""AstrBot 会话-对话管理器, 维护两个本地存储, 其中一个是 json 格式的shared_preferences, 另外一个是数据库.

在 AstrBot 中, 会话和对话是独立的, 会话用于标记对话窗口, 例如群聊"123456789"可以建立一个会话,
在一个会话中可以建立多个对话, 并且支持对话的切换和删除
"""

import json
from collections.abc import Awaitable, Callable

from deprecated import deprecated

from astrbot.core import sp
from astrbot.core.agent.conversation_events import (
    ConversationEventWriter,
    PluginConversationEvents,
    active_conversation_writer,
    active_plugin_id,
)
from astrbot.core.agent.message import AssistantMessageSegment, UserMessageSegment
from astrbot.core.db import BaseDatabase
from astrbot.core.db.conversation import ConversationConflictError, ConversationStore
from astrbot.core.db.po import (
    Conversation,
    ConversationData,
    ConversationRead,
    ConversationRevision,
)
from astrbot.core.utils.datetime_utils import to_utc_timestamp


class ConversationManager:
    """负责管理会话与 LLM 的对话，某个会话当前正在用哪个对话。"""

    def __init__(self, db_helper: BaseDatabase) -> None:
        self.session_conversations: dict[str, str] = {}
        self.db = db_helper
        self.save_interval = 60  # 每 60 秒保存一次

        # 会话删除回调函数列表（用于级联清理，如知识库配置）
        self._on_session_deleted_callbacks: list[Callable[[str], Awaitable[None]]] = []

    def get_conversation_events(self) -> PluginConversationEvents:
        """Access context writes and private events for the current plugin hook.

        Returns:
            Plugin facade bound to the current conversation and plugin identity.

        Raises:
            RuntimeError: No conversation-bound plugin hook is running.
        """
        writer = active_conversation_writer.get()
        plugin_id = active_plugin_id.get()
        if writer is None or plugin_id is None:
            raise RuntimeError(
                "Conversation events require an active conversation hook"
            )
        return writer.plugin(plugin_id)

    async def event_writer(
        self,
        unified_msg_origin: str,
        conversation_id: str,
        *,
        expected_revision: ConversationRevision | None = None,
    ) -> ConversationEventWriter:
        """Bind custom runners or plugins to an owned conversation revision.

        Args:
            unified_msg_origin: Owner UMO resolved by the host.
            conversation_id: Public conversation identity.
            expected_revision: Revision of the context used to prepare this request.

        Returns:
            A branch-bound writer implementing the common event protocol.

        Raises:
            ValueError: The conversation is missing or belongs to another UMO.
            ConversationConflictError: Context or branch changed during preparation.
        """
        active = active_conversation_writer.get()
        if (
            active
            and active.cid == conversation_id
            and active.umo == unified_msg_origin
        ):
            writer = active
        else:
            snapshot = await self.db.conversation_store.read(conversation_id)
            if snapshot is None or snapshot.conversation.umo != unified_msg_origin:
                raise ValueError("Conversation is not accessible")
            writer = ConversationEventWriter(self.db.conversation_store, snapshot)
        if expected_revision is not None and (
            expected_revision.head_seq != writer.head_seq
            or expected_revision.leaf_event_id != writer.leaf_event_id
        ):
            raise ConversationConflictError(
                "Conversation changed while preparing the request"
            )
        return writer

    async def fork_conversation(
        self, unified_msg_origin: str, source_event_id: str
    ) -> str:
        """Create a side conversation with an independent context snapshot.

        Args:
            unified_msg_origin: Owner UMO.
            source_event_id: Accessible historical position to copy.

        Returns:
            Public identity of the new conversation; selection is unchanged.
        """
        conv = await self.db.conversation_store.create(
            umo=unified_msg_origin,
            platform_id=unified_msg_origin.split(":", 1)[0],
            source_event_id=source_event_id,
        )
        return conv.conversation_id

    def register_on_session_deleted(
        self,
        callback: Callable[[str], Awaitable[None]],
    ) -> None:
        """注册会话删除回调函数.

        其他模块可以注册回调来响应会话删除事件，实现级联清理。
        例如：知识库模块可以注册回调来清理会话的知识库配置。

        Args:
            callback: 回调函数，接收会话ID (unified_msg_origin) 作为参数

        """
        self._on_session_deleted_callbacks.append(callback)

    async def _trigger_session_deleted(self, unified_msg_origin: str) -> None:
        """触发会话删除回调.

        Args:
            unified_msg_origin: 会话ID

        """
        for callback in self._on_session_deleted_callbacks:
            try:
                await callback(unified_msg_origin)
            except Exception as e:
                from astrbot.core import logger

                logger.error(
                    f"会话删除回调执行失败 (session: {unified_msg_origin}): {e}",
                )

    def _to_conversation(
        self,
        record: ConversationData,
        include_history: bool = True,
    ) -> Conversation:
        """Convert a database read result into the plugin-facing conversation.

        Args:
            record: Detached database read result or legacy conversation data.
            include_history: Whether to access and serialize the full history.

        Returns:
            Legacy-compatible conversation object.
        """
        created_ts = to_utc_timestamp(record.created_at)
        updated_ts = to_utc_timestamp(record.updated_at)
        created_at = int(created_ts) if created_ts is not None else 0
        updated_at = int(updated_ts) if updated_ts is not None else 0
        return Conversation(
            platform_id=record.platform_id,
            user_id=record.user_id,
            cid=record.conversation_id,
            history=json.dumps(record.content or []) if include_history else "[]",
            title=record.title,
            persona_id=record.persona_id,
            created_at=created_at,
            updated_at=updated_at,
            token_usage=record.token_usage,
            revision=record.revision if isinstance(record, ConversationRead) else None,
        )

    async def new_conversation(
        self,
        unified_msg_origin: str,
        platform_id: str | None = None,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> str:
        """新建对话，并将当前会话的对话转移到新对话.

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
        Returns:
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串

        """
        if not platform_id:
            # 如果没有提供 platform_id，则从 unified_msg_origin 中解析
            parts = unified_msg_origin.split(":")
            if len(parts) >= 3:
                platform_id = parts[0]
        if not platform_id:
            platform_id = "unknown"
        conv = await self.db.create_conversation(
            user_id=unified_msg_origin,
            platform_id=platform_id,
            content=content,
            title=title,
            persona_id=persona_id,
        )
        self.session_conversations[unified_msg_origin] = conv.conversation_id
        await sp.session_put(unified_msg_origin, "sel_conv_id", conv.conversation_id)
        return conv.conversation_id

    async def switch_conversation(
        self, unified_msg_origin: str, conversation_id: str
    ) -> None:
        """切换会话的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串

        """
        self.session_conversations[unified_msg_origin] = conversation_id
        await sp.session_put(unified_msg_origin, "sel_conv_id", conversation_id)

    async def delete_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str | None = None,
    ) -> None:
        """删除会话的对话，当 conversation_id 为 None 时删除会话当前的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串

        """
        if not conversation_id:
            conversation_id = await self.get_curr_conversation_id(unified_msg_origin)
        if conversation_id:
            await self.db.delete_conversation(cid=conversation_id)
            curr_cid = await self.get_curr_conversation_id(unified_msg_origin)
            if curr_cid == conversation_id:
                self.session_conversations.pop(unified_msg_origin, None)
                await sp.session_remove(unified_msg_origin, "sel_conv_id")

    async def delete_conversations_by_user_id(self, unified_msg_origin: str) -> None:
        """删除会话的所有对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id

        """
        await self.db.delete_conversations_by_user_id(user_id=unified_msg_origin)
        self.session_conversations.pop(unified_msg_origin, None)
        await sp.session_remove(unified_msg_origin, "sel_conv_id")

        # 触发会话删除回调（级联清理）
        await self._trigger_session_deleted(unified_msg_origin)

    async def get_curr_conversation_id(self, unified_msg_origin: str) -> str | None:
        """获取会话当前的对话 ID

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
        Returns:
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串

        """
        ret = self.session_conversations.get(unified_msg_origin, None)
        if not ret:
            ret = await sp.session_get(unified_msg_origin, "sel_conv_id", None)
            if ret:
                self.session_conversations[unified_msg_origin] = ret
        return ret

    async def get_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str,
        create_if_not_exists: bool = False,
    ) -> Conversation | None:
        """获取会话的对话.

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
            create_if_not_exists (bool): 如果对话不存在,是否创建一个新的对话
        Returns:
            conversation (Conversation): 对话对象

        """
        conv = await self.db.get_conversation_by_id(cid=conversation_id)
        if not conv and create_if_not_exists:
            # 如果对话不存在且需要创建，则新建一个对话
            conversation_id = await self.new_conversation(unified_msg_origin)
            conv = await self.db.get_conversation_by_id(cid=conversation_id)
        conv_res = None
        if conv:
            conv_res = self._to_conversation(conv)
        return conv_res

    async def get_conversations(
        self,
        unified_msg_origin: str | None = None,
        platform_id: str | None = None,
    ) -> list[Conversation]:
        """获取对话列表.

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id，可选
            platform_id (str): 平台 ID, 可选参数, 用于过滤对话
        Returns:
            conversations (List[Conversation]): 对话对象列表

        """
        convs = await self.db.get_conversations(
            user_id=unified_msg_origin,
            platform_id=platform_id,
        )
        convs_res = []
        for conv in convs:
            conv_res = self._to_conversation(conv)
            convs_res.append(conv_res)
        return convs_res

    async def get_filtered_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
        platform_ids: list[str] | None = None,
        search_query: str = "",
        include_history: bool = True,
        **kwargs,
    ) -> tuple[list[Conversation], int]:
        """获取过滤后的对话列表.

        Args:
            page (int): 页码, 默认为 1
            page_size (int): 每页大小, 默认为 20
            platform_ids (list[str]): 平台 ID 列表, 可选
            search_query (str): 搜索查询字符串, 可选
            include_history (bool): Whether to load the full conversation history.
        Returns:
            conversations (list[Conversation]): 对话对象列表

        """
        query_kwargs = {
            "page": page,
            "page_size": page_size,
            "platform_ids": platform_ids,
            "search_query": search_query,
            "include_history": include_history,
            **kwargs,
        }
        convs, cnt = await self.db.get_filtered_conversations(**query_kwargs)
        convs_res = []
        for conv in convs:
            conv_res = self._to_conversation(
                conv,
                include_history=include_history,
            )
            convs_res.append(conv_res)
        return convs_res, cnt

    async def update_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str | None = None,
        history: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
        token_usage: int | None = None,
    ) -> None:
        """更新会话的对话.

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
            history (List[Dict]): 对话历史记录, 是一个字典列表, 每个字典包含 role 和 content 字段
            token_usage (int | None): token 使用量。None 表示不更新

        """
        if not conversation_id:
            # 如果没有提供 conversation_id，则获取当前的
            conversation_id = await self.get_curr_conversation_id(unified_msg_origin)
        if conversation_id:
            writer = active_conversation_writer.get()
            if writer and writer.cid == conversation_id:
                if history is not None:
                    await writer.save_history(
                        history,
                        token_usage=token_usage,
                        origin="plugin" if active_plugin_id.get() else "unknown",
                    )
                changes = {}
                if title is not None:
                    changes["title"] = title
                if persona_id is not None:
                    changes["persona_id"] = persona_id
                if changes or (history is None and token_usage is not None):
                    payload = {"changes": changes}
                    if history is None and token_usage is not None:
                        payload["token_usage"] = token_usage
                    await writer.append("conversation.updated", payload)
                return
            if (
                history is not None
                and active_plugin_id.get()
                and isinstance(self.db.conversation_store, ConversationStore)
            ):
                # A hook may explicitly update another conversation it owns.
                target_writer = await self.event_writer(
                    unified_msg_origin, conversation_id
                )
                await target_writer.save_history(history, origin="plugin")
                history = None
            await self.db.update_conversation(
                cid=conversation_id,
                title=title,
                persona_id=persona_id,
                content=history,
                token_usage=token_usage,
            )

    @deprecated(reason="Use update_conversation() with the title parameter instead.")
    async def update_conversation_title(
        self,
        unified_msg_origin: str,
        title: str,
        conversation_id: str | None = None,
    ) -> None:
        """更新会话的对话标题.

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            title (str): 对话标题
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
        Deprecated:
            Use `update_conversation` with `title` parameter instead.

        """
        await self.update_conversation(
            unified_msg_origin=unified_msg_origin,
            conversation_id=conversation_id,
            title=title,
        )

    @deprecated(
        reason="Use update_conversation() with the persona_id parameter instead."
    )
    async def update_conversation_persona_id(
        self,
        unified_msg_origin: str,
        persona_id: str,
        conversation_id: str | None = None,
    ) -> None:
        """更新会话的对话 Persona ID.

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            persona_id (str): 对话 Persona ID
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
        Deprecated:
            Use `update_conversation` with `persona_id` parameter instead.

        """
        await self.update_conversation(
            unified_msg_origin=unified_msg_origin,
            conversation_id=conversation_id,
            persona_id=persona_id,
        )

    async def add_message_pair(
        self,
        cid: str,
        user_message: UserMessageSegment | dict,
        assistant_message: AssistantMessageSegment | dict,
    ) -> None:
        """Add a user-assistant message pair to the conversation history.

        Args:
            cid (str): Conversation ID
            user_message (UserMessageSegment | dict): OpenAI-format user message object or dict
            assistant_message (AssistantMessageSegment | dict): OpenAI-format assistant message object or dict

        Raises:
            Exception: If the conversation with the given ID is not found
        """
        if isinstance(self.db.conversation_store, ConversationStore):
            writer = active_conversation_writer.get()
            if writer and writer.cid == cid:
                messages = [
                    m.model_dump() if hasattr(m, "model_dump") else m
                    for m in (user_message, assistant_message)
                ]
                await writer.save_history(
                    [entry["message"] for entry in writer._entries] + messages
                )
                return
            snapshot = await self.db.conversation_store.read(cid)
            if snapshot is None:
                raise ValueError(f"Conversation with id {cid} not found")
            messages = [
                m.model_dump() if hasattr(m, "model_dump") else m
                for m in (user_message, assistant_message)
            ]
            await self.db.conversation_store.append(
                cid,
                [
                    {"type": "message.appended", "payload": {"message": message}}
                    for message in messages
                ],
                expected_head=snapshot.conversation.head_seq,
                expected_leaf=snapshot.conversation.leaf_event_id,
            )
            return
        conv = await self.db.get_conversation_by_id(cid=cid)
        if conv is None:
            raise ValueError(f"Conversation with id {cid} not found")
        history = conv.content or []
        history.extend(
            m.model_dump() if hasattr(m, "model_dump") else m
            for m in (user_message, assistant_message)
        )
        await self.db.update_conversation(cid=cid, content=history)

    async def get_human_readable_context(
        self,
        unified_msg_origin: str,
        conversation_id: str,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[str], int]:
        """获取人类可读的上下文.

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
            page (int): 页码
            page_size (int): 每页大小

        """
        conversation = await self.get_conversation(unified_msg_origin, conversation_id)
        if not conversation:
            return [], 0
        history = json.loads(conversation.history)

        # contexts_groups 存放按顺序的段落（每个段落是一个 str 列表），
        # 之后会被展平成一个扁平的 str 列表返回。
        contexts_groups: list[list[str]] = []
        temp_contexts: list[str] = []
        for record in history:
            if record["role"] == "user":
                temp_contexts.append(f"User: {record['content']}")
            elif record["role"] == "assistant":
                if record.get("content"):
                    temp_contexts.append(f"Assistant: {record['content']}")
                elif "tool_calls" in record:
                    tool_calls_str = json.dumps(
                        record["tool_calls"],
                        ensure_ascii=False,
                    )
                    temp_contexts.append(f"Assistant: [函数调用] {tool_calls_str}")
                else:
                    temp_contexts.append("Assistant: [未知的内容]")
                contexts_groups.insert(0, temp_contexts)
                temp_contexts = []

        # 展平分组后的 contexts 列表为单层字符串列表
        contexts = [item for sublist in contexts_groups for item in sublist]

        # 计算分页
        paged_contexts = contexts[(page - 1) * page_size : page * page_size]
        total_pages = len(contexts) // page_size
        if len(contexts) % page_size != 0:
            total_pages += 1

        return paged_contexts, total_pages
