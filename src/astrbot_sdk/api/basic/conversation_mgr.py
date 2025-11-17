from astr_agent_sdk.message import AssistantMessageSegment, UserMessageSegment
from ...api.basic.entities import Conversation


class BaseConversationManager:
    """负责管理会话与 LLM 的对话，某个会话当前正在用哪个对话。"""

    async def _trigger_session_deleted(self, unified_msg_origin: str) -> None:
        """触发会话删除回调.

        Args:
            unified_msg_origin: 会话ID

        """
        ...

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
        ...

    async def switch_conversation(
        self, unified_msg_origin: str, conversation_id: str
    ) -> None:
        """切换会话的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串

        """
        ...

    async def delete_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str | None = None,
    ):
        """删除会话的对话，当 conversation_id 为 None 时删除会话当前的对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串

        """
        ...

    async def delete_conversations_by_user_id(self, unified_msg_origin: str):
        """删除会话的所有对话

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id

        """
        ...

    async def get_curr_conversation_id(self, unified_msg_origin: str) -> str | None:
        """获取会话当前的对话 ID

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
        Returns:
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串

        """
        ...

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
        ...

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
        ...

    async def get_filtered_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
        platform_ids: list[str] | None = None,
        search_query: str = "",
        **kwargs,
    ) -> tuple[list[Conversation], int]:
        """获取过滤后的对话列表.

        Args:
            page (int): 页码, 默认为 1
            page_size (int): 每页大小, 默认为 20
            platform_ids (list[str]): 平台 ID 列表, 可选
            search_query (str): 搜索查询字符串, 可选
        Returns:
            conversations (list[Conversation]): 对话对象列表

        """
        ...

    async def update_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str | None = None,
        history: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> None:
        """更新会话的对话.

        Args:
            unified_msg_origin (str): 统一的消息来源字符串。格式为 platform_name:message_type:session_id
            conversation_id (str): 对话 ID, 是 uuid 格式的字符串
            history (List[Dict]): 对话历史记录, 是一个字典列表, 每个字典包含 role 和 content 字段

        """
        ...

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
        ...

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
        ...

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
        ...

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
        ...
