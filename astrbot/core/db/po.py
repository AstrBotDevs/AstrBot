import uuid

from datetime import datetime, timezone
from dataclasses import dataclass, field
from sqlmodel import (
    SQLModel,
    Text,
    JSON,
    UniqueConstraint,
    Field,
)
from typing import Optional, TypedDict


class PlatformStat(SQLModel, table=True):
    """This class represents the statistics of bot usage across different platforms.

    Note: In astrbot v4, we moved `platform` table to here.
    """

    __tablename__ = "platform_stats"

    id: int = Field(primary_key=True, sa_column_kwargs={"autoincrement": True})
    timestamp: datetime = Field(nullable=False)
    platform_id: str = Field(nullable=False)
    platform_type: str = Field(nullable=False)  # such as "aiocqhttp", "slack", etc.
    count: int = Field(default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "timestamp",
            "platform_id",
            "platform_type",
            name="uix_platform_stats",
        ),
    )


class ConversationV2(SQLModel, table=True):
    __tablename__ = "conversations"

    inner_conversation_id: int = Field(
        primary_key=True, sa_column_kwargs={"autoincrement": True}
    )
    conversation_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    platform_id: str = Field(nullable=False)
    user_id: str = Field(nullable=False)
    content: Optional[list] = Field(default=None, sa_type=JSON)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )
    title: Optional[str] = Field(default=None, max_length=255)
    persona_id: Optional[str] = Field(default=None)

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            name="uix_conversation_id",
        ),
    )


class Persona(SQLModel, table=True):
    """Persona is a set of instructions for LLMs to follow.

    It can be used to customize the behavior of LLMs.
    """

    __tablename__ = "personas"

    id: int = Field(primary_key=True, sa_column_kwargs={"autoincrement": True})
    persona_id: str = Field(max_length=255, nullable=False)
    system_prompt: str = Field(sa_type=Text, nullable=False)
    begin_dialogs: Optional[list] = Field(default=None, sa_type=JSON)
    """a list of strings, each representing a dialog to start with"""
    tools: Optional[list] = Field(default=None, sa_type=JSON)
    """None means use ALL tools for default, empty list means no tools, otherwise a list of tool names."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )

    __table_args__ = (
        UniqueConstraint(
            "persona_id",
            name="uix_persona_id",
        ),
    )


class Preference(SQLModel, table=True):
    """This class represents preferences for bots."""

    __tablename__ = "preferences"

    id: int | None = Field(
        default=None, primary_key=True, sa_column_kwargs={"autoincrement": True}
    )
    scope: str = Field(nullable=False)
    """Scope of the preference, such as 'global', 'umo', 'plugin'."""
    scope_id: str = Field(nullable=False)
    """ID of the scope, such as 'global', 'umo', 'plugin_name'."""
    key: str = Field(nullable=False)
    value: dict = Field(sa_type=JSON, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )

    __table_args__ = (
        UniqueConstraint(
            "scope",
            "scope_id",
            "key",
            name="uix_preference_scope_scope_id_key",
        ),
    )


class PlatformMessageHistory(SQLModel, table=True):
    """This class represents the message history for a specific platform.

    It is used to store messages that are not LLM-generated, such as user messages
    or platform-specific messages.
    """

    __tablename__ = "platform_message_history"

    id: int = Field(primary_key=True, sa_column_kwargs={"autoincrement": True})
    platform_id: str = Field(nullable=False)
    user_id: str = Field(nullable=False)  # An id of group, user in platform
    sender_id: Optional[str] = Field(default=None)  # ID of the sender in the platform
    sender_name: Optional[str] = Field(
        default=None
    )  # Name of the sender in the platform
    content: dict = Field(sa_type=JSON, nullable=False)  # a message chain list
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )


class Attachment(SQLModel, table=True):
    """This class represents attachments for messages in AstrBot.

    Attachments can be images, files, or other media types.
    """

    __tablename__ = "attachments"

    inner_attachment_id: int = Field(
        primary_key=True, sa_column_kwargs={"autoincrement": True}
    )
    attachment_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    path: str = Field(nullable=False)  # Path to the file on disk
    type: str = Field(nullable=False)  # Type of the file (e.g., 'image', 'file')
    mime_type: str = Field(nullable=False)  # MIME type of the file
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )

    __table_args__ = (
        UniqueConstraint(
            "attachment_id",
            name="uix_attachment_id",
        ),
    )


@dataclass
class Conversation:
    """LLM 对话类

    对于 WebChat，history 存储了包括指令、回复、图片等在内的所有消息。
    对于其他平台的聊天，不存储非 LLM 的回复（因为考虑到已经存储在各自的平台上）。

    在 v4.0.0 版本及之后，WebChat 的历史记录被迁移至 `PlatformMessageHistory` 表中，
    """

    platform_id: str
    user_id: str
    cid: str
    """对话 ID, 是 uuid 格式的字符串"""
    history: str = ""
    """字符串格式的对话列表。"""
    title: str | None = ""
    persona_id: str | None = ""
    created_at: int = 0
    updated_at: int = 0


class Personality(TypedDict):
    """LLM 人格类。

    在 v4.0.0 版本及之后，推荐使用上面的 Persona 类。并且， mood_imitation_dialogs 字段已被废弃。
    """

    prompt: str = ""
    name: str = ""
    begin_dialogs: list[str] = []
    mood_imitation_dialogs: list[str] = []
    """情感模拟对话预设。在 v4.0.0 版本及之后，已被废弃。"""
    tools: list[str] | None = None
    """工具列表。None 表示使用所有工具，空列表表示不使用任何工具"""

    # cache
    _begin_dialogs_processed: list[dict] = []
    _mood_imitation_dialogs_processed: str = ""


# ====
# Deprecated, and will be removed in future versions.
# ====


@dataclass
class Platform:
    """平台使用统计数据"""

    name: str
    count: int
    timestamp: int


@dataclass
class Stats:
    platform: list[Platform] = field(default_factory=list)
