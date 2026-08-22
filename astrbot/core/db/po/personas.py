import uuid
from datetime import datetime

from sqlmodel import JSON, Field, SQLModel, Text, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


class PersonaFolder(TimestampMixin, SQLModel, table=True):
    """Persona 文件夹，支持递归层级结构。

    用于组织和管理多个 Persona，类似于文件系统的目录结构。
    """

    __tablename__: str = "persona_folders"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    folder_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    name: str = Field(max_length=255, nullable=False)
    parent_id: str | None = Field(default=None, max_length=36)
    """父文件夹ID，NULL表示根目录"""
    description: str | None = Field(default=None, sa_type=Text)
    sort_order: int = Field(default=0)

    __table_args__ = (
        UniqueConstraint(
            "folder_id",
            name="uix_persona_folder_id",
        ),
    )


class Persona(TimestampMixin, SQLModel, table=True):
    """Persona is a set of instructions for LLMs to follow.

    It can be used to customize the behavior of LLMs.
    """

    __tablename__: str = "personas"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    persona_id: str = Field(max_length=255, nullable=False)
    system_prompt: str = Field(sa_type=Text, nullable=False)
    begin_dialogs: list | None = Field(default=None, sa_type=JSON)
    """a list of strings, each representing a dialog to start with"""
    tools: list | None = Field(default=None, sa_type=JSON)
    """None means use ALL tools for default, empty list means no tools, otherwise a list of tool names."""
    skills: list | None = Field(default=None, sa_type=JSON)
    """None means use ALL skills for default, empty list means no skills, otherwise a list of skill names."""
    custom_error_message: str | None = Field(default=None, sa_type=Text)
    """Optional custom error message sent to end users when the agent request fails."""
    folder_id: str | None = Field(default=None, max_length=36)
    """所属文件夹ID，NULL 表示在根目录"""
    sort_order: int = Field(default=0)
    """排序顺序"""

    __table_args__ = (
        UniqueConstraint(
            "persona_id",
            name="uix_persona_id",
        ),
    )


class PersonaSessionState(TimestampMixin, SQLModel, table=True):
    """Runtime state for one persona inside one chat stream."""

    __tablename__: str = "persona_session_states"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    persona_id: str = Field(max_length=255, nullable=False, index=True)
    umo: str = Field(max_length=512, nullable=False, index=True)
    agent_state: str = Field(default="running", max_length=32, nullable=False)
    talk_frequency_adjust: float = Field(default=1.0, nullable=False)
    consecutive_idle_count: int = Field(default=0, nullable=False)
    cooldown_until: datetime | None = Field(default=None)
    last_interaction_at: datetime | None = Field(default=None)
    last_proactive_at: datetime | None = Field(default=None)
    extra_state: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (
        UniqueConstraint(
            "persona_id",
            "umo",
            name="uix_persona_session_state_persona_umo",
        ),
    )


class PersonaExpressionAsset(TimestampMixin, SQLModel, table=True):
    """Learned expression style asset for one persona and scope."""

    __tablename__: str = "persona_expression_assets"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    persona_id: str = Field(max_length=255, nullable=False, index=True)
    scope: str = Field(max_length=512, nullable=False, index=True)
    trigger_scene: str = Field(max_length=128, nullable=False, index=True)
    style_text: str = Field(sa_type=Text, nullable=False)
    source_message_id: str = Field(max_length=255, nullable=False, index=True)
    score: float = Field(default=0.5, nullable=False)
    enabled: bool = Field(default=True, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "persona_id",
            "scope",
            "trigger_scene",
            "style_text",
            name="uix_persona_expression_asset",
        ),
    )


class PersonaJargonAsset(TimestampMixin, SQLModel, table=True):
    """Learned jargon or community term for one persona and scope."""

    __tablename__: str = "persona_jargon_assets"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    persona_id: str = Field(max_length=255, nullable=False, index=True)
    scope: str = Field(max_length=512, nullable=False, index=True)
    term: str = Field(max_length=128, nullable=False, index=True)
    meaning: str | None = Field(default=None, sa_type=Text)
    source_message_id: str = Field(max_length=255, nullable=False, index=True)
    score: float = Field(default=0.5, nullable=False)
    approved: bool = Field(default=False, nullable=False, index=True)
    enabled: bool = Field(default=True, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "persona_id",
            "scope",
            "term",
            name="uix_persona_jargon_asset",
        ),
    )


class PersonaBehaviorPolicy(TimestampMixin, SQLModel, table=True):
    """Learned behavior tendency for one persona and scope."""

    __tablename__: str = "persona_behavior_policies"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    persona_id: str = Field(max_length=255, nullable=False, index=True)
    scope: str = Field(max_length=512, nullable=False, index=True)
    situation: str = Field(max_length=255, nullable=False, index=True)
    preferred_action: str = Field(sa_type=Text, nullable=False)
    avoid_action: str | None = Field(default=None, sa_type=Text)
    confidence: float = Field(default=0.5, nullable=False)
    enabled: bool = Field(default=True, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "persona_id",
            "scope",
            "situation",
            "preferred_action",
            name="uix_persona_behavior_policy",
        ),
    )
