import abc
import datetime
import typing as T
from deprecated import deprecated
from dataclasses import dataclass
from astrbot.core.db.po import (
    Stats,
    PlatformStat,
    ConversationV2,
    PlatformMessageHistory,
    Attachment,
    Persona,
    Preference,
)
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


@dataclass
class BaseDatabase(abc.ABC):
    """
    数据库基类
    """

    DATABASE_URL = ""

    def __init__(self) -> None:
        self.engine = create_async_engine(
            self.DATABASE_URL,
            echo=False,
            future=True,
        )
        self.AsyncSessionLocal = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def initialize(self):
        """初始化数据库连接"""
        pass

    @asynccontextmanager
    async def get_db(self) -> T.AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        if not self.inited:
            await self.initialize()
            self.inited = True
        async with self.AsyncSessionLocal() as session:
            yield session

    @deprecated(version="4.0.0", reason="Use get_platform_stats instead")
    @abc.abstractmethod
    def get_base_stats(self, offset_sec: int = 86400) -> Stats:
        """获取基础统计数据"""
        raise NotImplementedError

    @deprecated(version="4.0.0", reason="Use get_platform_stats instead")
    @abc.abstractmethod
    def get_total_message_count(self) -> int:
        """获取总消息数"""
        raise NotImplementedError

    @deprecated(version="4.0.0", reason="Use get_platform_stats instead")
    @abc.abstractmethod
    def get_grouped_base_stats(self, offset_sec: int = 86400) -> Stats:
        """获取基础统计数据(合并)"""
        raise NotImplementedError

    # New methods in v4.0.0

    @abc.abstractmethod
    async def insert_platform_stats(
        self,
        platform_id: str,
        platform_type: str,
        count: int = 1,
        timestamp: datetime.datetime | None = None,
    ) -> None:
        """Insert a new platform statistic record."""
        ...

    @abc.abstractmethod
    async def count_platform_stats(self) -> int:
        """Count the number of platform statistics records."""
        ...

    @abc.abstractmethod
    async def get_platform_stats(self, offset_sec: int = 86400) -> list[PlatformStat]:
        """Get platform statistics within the specified offset in seconds and group by platform_id."""
        ...

    @abc.abstractmethod
    async def get_conversations(
        self, user_id: str | None = None, platform_id: str | None = None
    ) -> list[ConversationV2]:
        """Get all conversations for a specific user and platform_id(optional).

        content is not included in the result.
        """
        ...

    @abc.abstractmethod
    async def get_conversation_by_id(self, cid: str) -> ConversationV2:
        """Get a specific conversation by its ID."""
        ...

    @abc.abstractmethod
    async def get_all_conversations(
        self, page: int = 1, page_size: int = 20
    ) -> list[ConversationV2]:
        """Get all conversations with pagination."""
        ...

    @abc.abstractmethod
    async def get_filtered_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
        platform_ids: list[str] | None = None,
        search_query: str = "",
        **kwargs,
    ) -> tuple[list[ConversationV2], int]:
        """Get conversations filtered by platform IDs and search query."""
        ...

    @abc.abstractmethod
    async def create_conversation(
        self,
        user_id: str,
        platform_id: str,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
        cid: str | None = None,
        created_at: datetime.datetime | None = None,
        updated_at: datetime.datetime | None = None,
    ) -> ConversationV2:
        """Create a new conversation."""
        ...

    @abc.abstractmethod
    async def update_conversation(
        self,
        cid: str,
        title: str | None = None,
        persona_id: str | None = None,
        content: list[dict] | None = None,
    ) -> None:
        """Update a conversation's history."""
        ...

    @abc.abstractmethod
    async def delete_conversation(self, cid: str) -> None:
        """Delete a conversation by its ID."""
        ...

    @abc.abstractmethod
    async def insert_platform_message_history(
        self,
        platform_id: str,
        user_id: str,
        content: list[dict],
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> None:
        """Insert a new platform message history record."""
        ...

    @abc.abstractmethod
    async def delete_platform_message_offset(
        self, platform_id: str, user_id: str, offset_sec: int = 86400
    ) -> None:
        """Delete platform message history records older than the specified offset."""
        ...

    @abc.abstractmethod
    async def get_platform_message_history(
        self,
        platform_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[PlatformMessageHistory]:
        """Get platform message history for a specific user."""
        ...

    @abc.abstractmethod
    async def insert_attachment(
        self,
        path: str,
        type: str,
        mime_type: str,
    ):
        """Insert a new attachment record."""
        ...

    @abc.abstractmethod
    async def get_attachment_by_id(self, attachment_id: str) -> Attachment:
        """Get an attachment by its ID."""
        ...

    @abc.abstractmethod
    async def insert_persona(
        self,
        persona_id: str,
        system_prompt: str,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None = None,
    ) -> Persona:
        """Insert a new persona record."""
        ...

    @abc.abstractmethod
    async def get_persona_by_id(self, persona_id: str) -> Persona:
        """Get a persona by its ID."""
        ...

    @abc.abstractmethod
    async def get_personas(self) -> list[Persona]:
        """Get all personas for a specific bot."""
        ...

    @abc.abstractmethod
    async def update_persona(
        self,
        persona_id: str,
        system_prompt: str | None = None,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None = None,
    ) -> Persona | None:
        """Update a persona's system prompt or begin dialogs."""
        ...

    @abc.abstractmethod
    async def delete_persona(self, persona_id: str) -> None:
        """Delete a persona by its ID."""
        ...

    @abc.abstractmethod
    async def insert_preference_or_update(
        self, scope: str, scope_id: str, key: str, value: dict
    ) -> Preference:
        """Insert a new preference record."""
        ...

    @abc.abstractmethod
    async def get_preference(self, scope: str, scope_id: str, key: str) -> Preference:
        """Get a preference by scope ID and key."""
        ...

    @abc.abstractmethod
    async def get_preferences(
        self, scope: str, scope_id: str | None = None, key: str | None = None
    ) -> list[Preference]:
        """Get all preferences for a specific scope ID or key."""
        ...

    @abc.abstractmethod
    async def remove_preference(self, scope: str, scope_id: str, key: str) -> None:
        """Remove a preference by scope ID and key."""
        ...

    @abc.abstractmethod
    async def clear_preferences(self, scope: str, scope_id: str) -> None:
        """Clear all preferences for a specific scope ID."""
        ...

    # @abc.abstractmethod
    # async def insert_llm_message(
    #     self,
    #     cid: str,
    #     role: str,
    #     content: list,
    #     tool_calls: list = None,
    #     tool_call_id: str = None,
    #     parent_id: str = None,
    # ) -> LLMMessage:
    #     """Insert a new LLM message into the conversation."""
    #     ...

    # @abc.abstractmethod
    # async def get_llm_messages(self, cid: str) -> list[LLMMessage]:
    #     """Get all LLM messages for a specific conversation."""
    #     ...
