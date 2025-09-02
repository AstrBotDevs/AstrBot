"""
AstrBot 会话-对话管理器, 维护两个本地存储, 其中一个是 json 格式的shared_preferences, 另外一个是数据库

在 AstrBot 中, 会话和对话是独立的, 会话用于标记对话窗口, 例如群聊"123456789"可以建立一个会话,
在一个会话中可以建立多个对话, 并且支持对话的切换和删除
"""

import json
from astrbot.core import sp
from typing import Dict, List
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import Conversation, ConversationV2


class ConversationManager:
    """负责管理会话与 LLM 的对话，某个会话当前正在用哪个对话。"""

    def __init__(self, db_helper: BaseDatabase):
        self.session_conversations: Dict[str, str] = {}
        self.db = db_helper
        self.save_interval = 60  # 每 60 秒保存一次

    def _convert_conv_from_v2_to_v1(self, conv_v2: ConversationV2) -> Conversation:
        """将 ConversationV2 对象转换为 Conversation 对象"""
        created_at = int(conv_v2.created_at.timestamp())
        updated_at = int(conv_v2.updated_at.timestamp())
        return Conversation(
            platform_id=conv_v2.platform_id,
            user_id=conv_v2.user_id,
            cid=conv_v2.conversation_id,
            history=json.dumps(conv_v2.content or []),
            title=conv_v2.title,
            persona_id=conv_v2.persona_id,
            created_at=created_at,
            updated_at=updated_at,
        )

    async def new_conversation(
        self,
        unified_msg_origin: str,
        platform_id: str | None = None,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> str:
        """新建对话，并将当前会话的对话转移到新对话

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

    async def switch_conversation(self, unified_msg_origin: str, conversation_id: str):
        """切换会话的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
        """
        self.session_conversations[unified_msg_origin] = conversation_id
        await sp.session_put(unified_msg_origin, "sel_conv_id", conversation_id)

    async def delete_conversation(
        self, unified_msg_origin: str, conversation_id: str | None = None
    ):
        """删除会话的对话，当 conversation_id 为 None 时删除会话当前的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
        """
        f = False
        if not conversation_id:
            conversation_id = self.session_conversations.get(unified_msg_origin)
            if conversation_id:
                f = True
        if conversation_id:
            await self.db.delete_conversation(cid=conversation_id)
            if f:
                self.session_conversations.pop(unified_msg_origin, None)
                await sp.session_remove(unified_msg_origin, "sel_conv_id")

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
        """获取会话的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
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
            conv_res = self._convert_conv_from_v2_to_v1(conv)
        return conv_res

    async def get_conversations(
        self, unified_msg_origin: str | None = None, platform_id: str | None = None
    ) -> List[Conversation]:
        """获取对话列表

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id，可选
            platform_id (str): 平台 ID, 可选参数, 用于过滤对话
        Returns:
            conversations (List[Conversation]): 对话对象列表
        """
        convs = await self.db.get_conversations(
            user_id=unified_msg_origin, platform_id=platform_id
        )
        convs_res = []
        for conv in convs:
            conv_res = self._convert_conv_from_v2_to_v1(conv)
            convs_res.append(conv_res)
        return convs_res

    async def get_filtered_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
        platform_ids: list[str] | None = None,
        search_query: str = "",
        **kwargs,
    ) -> tuple[list[Conversation], int]:
        """获取过滤后的对话列表

        Args:
            page (int): 页码, 默认为 1
            page_size (int): 每页大小, 默认为 20
            platform_ids (list[str]): 平台 ID 列表, 可选
            search_query (str): 搜索查询字符串, 可选
        Returns:
            conversations (list[Conversation]): 对话对象列表
        """
        convs, cnt = await self.db.get_filtered_conversations(
            page=page,
            page_size=page_size,
            platform_ids=platform_ids,
            search_query=search_query,
            **kwargs,
        )
        convs_res = []
        for conv in convs:
            conv_res = self._convert_conv_from_v2_to_v1(conv)
            convs_res.append(conv_res)
        return convs_res, cnt

    async def update_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str | None = None,
        history: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ):
        """更新会话的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
            history (List[Dict]): 对话历史记录, 是一个字典列表, 每个字典包含 role 和 content 字段
        """
        if not conversation_id:
            # 如果没有提供 conversation_id，则获取当前的
            conversation_id = await self.get_curr_conversation_id(unified_msg_origin)
        if conversation_id:
            await self.db.update_conversation(
                cid=conversation_id,
                title=title,
                persona_id=persona_id,
                content=history,
            )

    async def update_conversation_title(
        self, unified_msg_origin: str, title: str, conversation_id: str | None = None
    ):
        """更新会话的对话标题

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            title (str): 对话标题

        Deprecated:
            Use `update_conversation` with `title` parameter instead.
        """
        await self.update_conversation(
            unified_msg_origin=unified_msg_origin,
            conversation_id=conversation_id,
            title=title,
        )

    async def update_conversation_persona_id(
        self,
        unified_msg_origin: str,
        persona_id: str,
        conversation_id: str | None = None,
    ):
        """更新会话的对话 Persona ID

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            persona_id (str): 对话 Persona ID

        Deprecated:
            Use `update_conversation` with `persona_id` parameter instead.
        """
        await self.update_conversation(
            unified_msg_origin=unified_msg_origin,
            conversation_id=conversation_id,
            persona_id=persona_id,
        )

    async def get_human_readable_context(
        self, unified_msg_origin, conversation_id, page=1, page_size=10
    ):
        """获取人类可读的上下文

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
            page (int): 页码
            page_size (int): 每页大小
        """
        conversation = await self.get_conversation(unified_msg_origin, conversation_id)
        history = json.loads(conversation.history)

        contexts = []
        temp_contexts = []
        for record in history:
            if record["role"] == "user":
                temp_contexts.append(f"User: {record['content']}")
            elif record["role"] == "assistant":
                if "content" in record and record["content"]:
                    temp_contexts.append(f"Assistant: {record['content']}")
                elif "tool_calls" in record:
                    tool_calls_str = json.dumps(
                        record["tool_calls"], ensure_ascii=False
                    )
                    temp_contexts.append(f"Assistant: [函数调用] {tool_calls_str}")
                else:
                    temp_contexts.append("Assistant: [未知的内容]")
                contexts.insert(0, temp_contexts)
                temp_contexts = []

        # 展平 contexts 列表
        contexts = [item for sublist in contexts for item in sublist]

        # 计算分页
        paged_contexts = contexts[(page - 1) * page_size : page * page_size]
        total_pages = len(contexts) // page_size
        if len(contexts) % page_size != 0:
            total_pages += 1

        return paged_contexts, total_pages
