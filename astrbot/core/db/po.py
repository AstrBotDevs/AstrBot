from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from dataclasses import dataclass

Base = declarative_base()


class PlatformStat(Base):
    """This class represents the statistics of bot usage across different platforms.

    Note: In astrbot v4, we moved `platform` table to here.
    """

    __tablename__ = "platform_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)  # primary key
    timestamp = Column(DateTime, nullable=False)
    bot_id = Column(Integer, nullable=False)
    platform_id = Column(Integer, nullable=False)
    platform_type = Column(String, nullable=False)  # such as "aiocqhttp", "slack", etc.
    count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "timestamp",
            "platform_id",
            "bot_id",
            "platform_type",
            name="uix_platform_stats",
        ),
    )


class ConversationV2(Base):
    __tablename__ = "conversations"

    conversation_id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, nullable=False)
    platform_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )
    title = Column(String(255), nullable=True)
    persona_id = Column(Integer, nullable=True)

    # Relationships
    messages = relationship("LLMMessage", back_populates="conversation")


class LLMMessage(Base):
    """This class represents the LLM message data for conversations in AstrBot."""

    __tablename__ = "llm_messages"

    message_id = Column(Integer, primary_key=True, autoincrement=True)  # primary key
    conversation_id = Column(
        Integer, ForeignKey("conversations.conversation_id"), nullable=False
    )
    parent_id = Column(Integer, ForeignKey("llm_messages.message_id"), nullable=True)
    role = Column(String, nullable=False)  # e.g., 'user', 'assistant', 'system'
    content = Column(JSON, nullable=False)  # stores content as a JSON-encoded list
    tool_calls = Column(JSON, nullable=True)  # stores tool calls as a JSON-encoded list
    tool_call_id = Column(Integer, nullable=True)  # ID for the specific tool call
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)

    # Relationships
    conversation = relationship("ConversationV2", back_populates="messages")
    parent_message = relationship(
        "LLMMessage", remote_side=[message_id], backref="child_messages"
    )


class Persona(Base):
    """Persona is a set of instructions for LLMs to follow.

    It can be used to customize the behavior of LLMs.
    """

    __tablename__ = "personas"

    persona_id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    system_prompt = Column(Text, nullable=False)
    begin_dialogs = Column(Text, nullable=True)
    """a list of strings, each representing a dialog to start with"""
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )


@dataclass
class Conversation:
    """LLM 对话存储

    对于网页聊天，history 存储了包括指令、回复、图片等在内的所有消息。
    对于其他平台的聊天，不存储非 LLM 的回复（因为考虑到已经存储在各自的平台上）。

    deprecated: v4.0.0, use ConversationV2 model instead.
    """

    user_id: str
    cid: str
    history: str = ""
    """字符串格式的列表。"""
    created_at: int = 0
    updated_at: int = 0
    title: str = ""
    persona_id: str = ""
