import abc
import datetime
import typing as T
from contextlib import asynccontextmanager
from dataclasses import dataclass

from deprecated import deprecated
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from astrbot.core.db.po import (
    Attachment,
    ConversationV2,
    Persona,
    PlatformMessageHistory,
    PlatformSession,
    PlatformStat,
    Preference,
    Stats,
)


@dataclass
class BaseDatabase(abc.ABC):
    """数据库基类"""

    DATABASE_URL = ""

    def __init__(self) -> None:
        self.engine = create_async_engine(
            self.DATABASE_URL,
            echo=False,
            future=True,
        )
        self.AsyncSessionLocal = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def initialize(self):
        """初始化数据库连接"""

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
        self,
        user_id: str | None = None,
        platform_id: str | None = None,
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
        self,
        page: int = 1,
        page_size: int = 20,
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
    async def delete_conversations_by_user_id(self, user_id: str) -> None:
        """Delete all conversations for a specific user."""
        ...

    @abc.abstractmethod
    async def insert_platform_message_history(
        self,
        platform_id: str,
        user_id: str,
        content: dict,
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> PlatformMessageHistory:
        """Insert a new platform message history record."""
        ...

    @abc.abstractmethod
    async def delete_platform_message_offset(
        self,
        platform_id: str,
        user_id: str,
        offset_sec: int = 86400,
    ) -> None:
        """Delete platform message history records newer than the specified offset."""
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
    async def get_platform_message_history_by_id(
        self,
        message_id: int,
    ) -> PlatformMessageHistory | None:
        """Get a platform message history record by its ID."""
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
    async def get_attachments(self, attachment_ids: list[str]) -> list[Attachment]:
        """Get multiple attachments by their IDs."""
        ...

    @abc.abstractmethod
    async def delete_attachment(self, attachment_id: str) -> bool:
        """Delete an attachment by its ID.

        Returns True if the attachment was deleted, False if it was not found.
        """
        ...

    @abc.abstractmethod
    async def delete_attachments(self, attachment_ids: list[str]) -> int:
        """Delete multiple attachments by their IDs.

        Returns the number of attachments deleted.
        """
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
        self,
        scope: str,
        scope_id: str,
        key: str,
        value: dict,
    ) -> Preference:
        """Insert a new preference record."""
        ...

    @abc.abstractmethod
    async def get_preference(self, scope: str, scope_id: str, key: str) -> Preference:
        """Get a preference by scope ID and key."""
        ...

    @abc.abstractmethod
    async def get_preferences(
        self,
        scope: str,
        scope_id: str | None = None,
        key: str | None = None,
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

    @abc.abstractmethod
    async def get_session_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
        search_query: str | None = None,
        platform: str | None = None,
    ) -> tuple[list[dict], int]:
        """Get paginated session conversations with joined conversation and persona details, support search and platform filter."""
        ...

    # ====
    # Platform Session Management
    # ====

    @abc.abstractmethod
    async def create_platform_session(
        self,
        creator: str,
        platform_id: str = "webchat",
        session_id: str | None = None,
        display_name: str | None = None,
        is_group: int = 0,
    ) -> PlatformSession:
        """Create a new Platform session."""
        ...

    @abc.abstractmethod
    async def get_platform_session_by_id(
        self, session_id: str
    ) -> PlatformSession | None:
        """Get a Platform session by its ID."""
        ...

    @abc.abstractmethod
    async def get_platform_sessions_by_creator(
        self,
        creator: str,
        platform_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[PlatformSession]:
        """Get all Platform sessions for a specific creator (username) and optionally platform."""
        ...

    @abc.abstractmethod
    async def update_platform_session(
        self,
        session_id: str,
        display_name: str | None = None,
    ) -> None:
        """Update a Platform session's updated_at timestamp and optionally display_name."""
        ...

    @abc.abstractmethod
    async def delete_platform_session(self, session_id: str) -> None:
        """Delete a Platform session by its ID."""
        ...
