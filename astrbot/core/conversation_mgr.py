"""
AstrBot 会话-对话管理器, 维护两个本地存储, 其中一个是 json 格式的shared_preferences, 另外一个是数据库

在 AstrBot 中, 会话和对话是独立的, 会话用于标记对话窗口, 例如群聊"123456789"可以建立一个会话,
在一个会话中可以建立多个对话, 并且支持对话的切换和删除
"""

import uuid
import json
import asyncio
from astrbot.core import sp
from typing import Dict, List
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import Conversation


class ConversationManager:
    """负责管理会话与 LLM 的对话，某个会话当前正在用哪个对话。"""

    def __init__(self, db_helper: BaseDatabase):
        # session_conversations 字典记录会话ID-对话ID 映射关系
        self.session_conversations: Dict[str, str] = sp.get("session_conversation", {})
        self.db = db_helper
        self.save_interval = 60  # 每 60 秒保存一次
        self._start_periodic_save()

    def _start_periodic_save(self):
        """启动定时保存任务"""
        asyncio.create_task(self._periodic_save())

    async def _periodic_save(self):
        """定时保存会话对话映射关系到存储中"""
        while True:
            await asyncio.sleep(self.save_interval)
            self._save_to_storage()

    def _save_to_storage(self):
        """保存会话对话映射关系到存储中"""
        sp.put("session_conversation", self.session_conversations)

    async def new_conversation(self, unified_msg_origin: str) -> str:
        """新建对话，并将当前会话的对话转移到新对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
        Returns:
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
        """
        conversation_id = str(uuid.uuid4())
        self.db.new_conversation(user_id=unified_msg_origin, cid=conversation_id)
        self.session_conversations[unified_msg_origin] = conversation_id
        sp.put("session_conversation", self.session_conversations)
        return conversation_id

    async def switch_conversation(self, unified_msg_origin: str, conversation_id: str):
        """切换会话的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
        """
        self.session_conversations[unified_msg_origin] = conversation_id
        sp.put("session_conversation", self.session_conversations)

    async def delete_conversation(
        self, unified_msg_origin: str, conversation_id: str = None
    ):
        """删除会话的对话，当 conversation_id 为 None 时删除会话当前的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
        """
        conversation_id = self.session_conversations.get(unified_msg_origin)
        if conversation_id:
            self.db.delete_conversation(user_id=unified_msg_origin, cid=conversation_id)
            del self.session_conversations[unified_msg_origin]
            sp.put("session_conversation", self.session_conversations)

    async def get_curr_conversation_id(self, unified_msg_origin: str) -> str:
        """获取会话当前的对话 ID

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
        Returns:
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
        """
        return self.session_conversations.get(unified_msg_origin, None)

    async def get_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str,
        create_if_not_exists: bool = False,
    ) -> Conversation:
        """获取会话的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
        Returns:
            conversation (Conversation): 对话对象
        """
        conv = self.db.get_conversation_by_user_id(unified_msg_origin, conversation_id)
        if not conv and create_if_not_exists:
            # 如果对话不存在且需要创建，则新建一个对话
            conversation_id = await self.new_conversation(unified_msg_origin)
            return self.db.get_conversation_by_user_id(
                unified_msg_origin, conversation_id
            )
        return self.db.get_conversation_by_user_id(unified_msg_origin, conversation_id)

    async def get_conversations(self, unified_msg_origin: str) -> List[Conversation]:
        """获取会话的所有对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
        Returns:
            conversations (List[Conversation]): 对话对象列表
        """
        return self.db.get_conversations(unified_msg_origin)

    async def update_conversation(
        self, unified_msg_origin: str, conversation_id: str, history: List[Dict]
    ):
        """更新会话的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
            history (List[Dict]): 对话历史记录, 是一个字典列表, 每个字典包含 role 和 content 字段
        """
        if conversation_id:
            self.db.update_conversation(
                user_id=unified_msg_origin,
                cid=conversation_id,
                history=json.dumps(history),
            )

    async def update_conversation_title(self, unified_msg_origin: str, title: str):
        """更新会话的对话标题

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            title (str): 对话标题
        """
        conversation_id = self.session_conversations.get(unified_msg_origin)
        if conversation_id:
            self.db.update_conversation_title(
                user_id=unified_msg_origin, cid=conversation_id, title=title
            )

    async def update_conversation_persona_id(
        self, unified_msg_origin: str, persona_id: str
    ):
        """更新会话的对话 Persona ID

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            persona_id (str): 对话 Persona ID
        """
        conversation_id = self.session_conversations.get(unified_msg_origin)
        if conversation_id:
            self.db.update_conversation_persona_id(
                user_id=unified_msg_origin, cid=conversation_id, persona_id=persona_id
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
