import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict

from sqlmodel import JSON, Field, Index, SQLModel, Text, UniqueConstraint


class TimestampMixin(SQLModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )


class PlatformStat(SQLModel, table=True):
    """This class represents the statistics of bot usage across different platforms.

    Note: In astrbot v4, we moved `platform` table to here.
    """

    __tablename__: str = "platform_stats"

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


class ProviderStat(TimestampMixin, SQLModel, table=True):
    """Per-response provider stats for internal agent runs."""

    __tablename__: str = "provider_stats"

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    agent_type: str = Field(default="internal", nullable=False, index=True)
    status: str = Field(default="completed", nullable=False, index=True)
    umo: str = Field(nullable=False, index=True)
    conversation_id: str | None = Field(default=None, index=True)
    provider_id: str = Field(nullable=False, index=True)
    provider_model: str | None = Field(default=None, index=True)
    token_input_other: int = Field(default=0, nullable=False)
    token_input_cached: int = Field(default=0, nullable=False)
    token_output: int = Field(default=0, nullable=False)
    start_time: float = Field(default=0.0, nullable=False)
    end_time: float = Field(default=0.0, nullable=False)
    time_to_first_token: float = Field(default=0.0, nullable=False)


class ConversationV2(TimestampMixin, SQLModel, table=True):
    __tablename__: str = "conversations"

    inner_conversation_id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    conversation_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    platform_id: str = Field(nullable=False)
    user_id: str = Field(nullable=False)
    content: list | None = Field(default=None, sa_type=JSON)

    title: str | None = Field(default=None, max_length=255)
    persona_id: str | None = Field(default=None)
    token_usage: int = Field(default=0, nullable=False)
    """content is a list of OpenAI-formated messages in list[dict] format.
    token_usage is the total token value of the messages.
    when 0, will use estimated token counter.
    """

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            name="uix_conversation_id",
        ),
    )


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


class MemoryFact(TimestampMixin, SQLModel, table=True):
    """A remembered person fact scoped to its source chat stream."""

    __tablename__: str = "memory_facts"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    person_id: str = Field(max_length=255, nullable=False, index=True)
    chat_id: str = Field(max_length=512, nullable=False, index=True)
    scope_id: str = Field(max_length=512, nullable=False, index=True)
    fact_text: str = Field(sa_type=Text, nullable=False)
    fact_type: str = Field(default="preference", max_length=64, nullable=False)
    source_message_id: str = Field(max_length=255, nullable=False, index=True)
    evidence_message_ids: list = Field(default_factory=list, sa_type=JSON)
    confidence: float = Field(default=0.6, nullable=False)
    status: str = Field(default="active", max_length=32, nullable=False, index=True)
    ttl_at: datetime | None = Field(default=None)

    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "chat_id",
            "fact_text",
            name="uix_memory_fact_person_chat_text",
        ),
        UniqueConstraint(
            "source_message_id",
            "fact_text",
            name="uix_memory_fact_source_text",
        ),
    )


class MemoryProfile(TimestampMixin, SQLModel, table=True):
    """Aggregated person profile for one memory scope."""

    __tablename__: str = "memory_profiles"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    person_id: str = Field(max_length=255, nullable=False, index=True)
    chat_scope: str = Field(max_length=512, nullable=False, index=True)
    profile_text: str = Field(sa_type=Text, nullable=False)
    source_version: int = Field(default=1, nullable=False)
    is_override: bool = Field(default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "chat_scope",
            "is_override",
            name="uix_memory_profile_person_scope_override",
        ),
    )


class MemoryEpisode(TimestampMixin, SQLModel, table=True):
    """A compact event memory built from one or more chat turns."""

    __tablename__: str = "memory_episodes"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    episode_id: str = Field(
        max_length=64,
        nullable=False,
        unique=True,
    )
    chat_id: str = Field(max_length=512, nullable=False, index=True)
    scope_id: str = Field(max_length=512, nullable=False, index=True)
    title: str = Field(max_length=255, nullable=False)
    summary: str = Field(sa_type=Text, nullable=False)
    participant_ids: list = Field(default_factory=list, sa_type=JSON)
    start_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    end_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    source_message_ids: list = Field(default_factory=list, sa_type=JSON)
    status: str = Field(default="active", max_length=32, nullable=False, index=True)


class MemoryScopePolicyRecord(TimestampMixin, SQLModel, table=True):
    """Explicit memory sharing rule between isolated chat scopes."""

    __tablename__: str = "memory_scope_policies"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    owner_scope_id: str = Field(max_length=512, nullable=False, index=True)
    target_scope_id: str = Field(max_length=512, nullable=False, index=True)
    sharing_mode: str = Field(default="group-shared", max_length=32, nullable=False)
    enabled: bool = Field(default=True, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "owner_scope_id",
            "target_scope_id",
            "sharing_mode",
            name="uix_memory_scope_policy_owner_target_mode",
        ),
    )


class MemoryTuningTask(TimestampMixin, SQLModel, table=True):
    """Recorded retrieval tuning probe for one memory scope."""

    __tablename__: str = "memory_tuning_tasks"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    task_id: str = Field(max_length=64, nullable=False, unique=True)
    task_type: str = Field(default="retrieval_probe", max_length=64, nullable=False)
    target_scope: str = Field(max_length=512, nullable=False, index=True)
    candidate_config: dict = Field(default_factory=dict, sa_type=JSON)
    evaluation_result: dict = Field(default_factory=dict, sa_type=JSON)
    status: str = Field(default="pending", max_length=32, nullable=False, index=True)


class MemoryOperationLog(TimestampMixin, SQLModel, table=True):
    """Audit log for memory writes and maintenance operations."""

    __tablename__: str = "memory_operation_logs"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    operation_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    operator: str = Field(max_length=255, nullable=False)
    target_type: str = Field(max_length=64, nullable=False, index=True)
    target_id: str = Field(max_length=255, nullable=False, index=True)
    action: str = Field(max_length=64, nullable=False, index=True)
    reason: str | None = Field(default=None, sa_type=Text)
    payload: dict = Field(default_factory=dict, sa_type=JSON)


class CronJob(TimestampMixin, SQLModel, table=True):
    """Cron job definition for scheduler and WebUI management."""

    __tablename__: str = "cron_jobs"

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    job_id: str = Field(
        max_length=64,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    name: str = Field(max_length=255, nullable=False)
    description: str | None = Field(default=None, sa_type=Text)
    job_type: str = Field(max_length=32, nullable=False)  # basic | active_agent
    cron_expression: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, max_length=64)
    payload: dict = Field(default_factory=dict, sa_type=JSON)
    enabled: bool = Field(default=True)
    persistent: bool = Field(default=True)
    run_once: bool = Field(default=False)
    status: str = Field(default="scheduled", max_length=32)
    last_run_at: datetime | None = Field(default=None)
    next_run_time: datetime | None = Field(default=None)
    last_error: str | None = Field(default=None, sa_type=Text)


class Preference(TimestampMixin, SQLModel, table=True):
    """This class represents preferences for bots."""

    __tablename__: str = "preferences"

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    scope: str = Field(nullable=False)
    """Scope of the preference, such as 'global', 'umo', 'plugin'."""
    scope_id: str = Field(nullable=False)
    """ID of the scope, such as 'global', 'umo', 'plugin_name'."""
    key: str = Field(nullable=False)
    value: dict = Field(sa_type=JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "scope",
            "scope_id",
            "key",
            name="uix_preference_scope_scope_id_key",
        ),
    )


class PlatformMessageHistory(TimestampMixin, SQLModel, table=True):
    """This class represents the message history for a specific platform.

    It is used to store messages that are not LLM-generated, such as user messages
    or platform-specific messages.
    """

    __tablename__: str = "platform_message_history"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    platform_id: str = Field(nullable=False)
    user_id: str = Field(nullable=False)  # An id of group, user in platform
    sender_id: str | None = Field(default=None)  # ID of the sender in the platform
    sender_name: str | None = Field(
        default=None,
    )  # Name of the sender in the platform
    content: dict = Field(sa_type=JSON, nullable=False)  # a message chain list
    role: str = Field(default="user", nullable=False)
    """Normalized message role: ``user``, ``assistant`` or ``system``."""
    is_group: bool = Field(default=False, nullable=False, index=True)
    """Whether this row belongs to an isolated group-message history."""
    llm_checkpoint_id: str | None = Field(default=None, index=True)

    __table_args__ = (
        Index(
            "ix_platform_message_history_scope_order",
            "platform_id",
            "user_id",
            "is_group",
            "id",
        ),
    )


class WebChatThread(TimestampMixin, SQLModel, table=True):
    """A side thread created from a selected WebChat assistant response."""

    __tablename__: str = "webchat_threads"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    thread_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    creator: str = Field(nullable=False, index=True)
    parent_session_id: str = Field(nullable=False, index=True)
    parent_message_id: int = Field(nullable=False, index=True)
    base_checkpoint_id: str = Field(nullable=False, index=True)
    selected_text: str = Field(sa_type=Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "thread_id",
            name="uix_webchat_thread_id",
        ),
    )


class PlatformSession(TimestampMixin, SQLModel, table=True):
    """Platform session table for managing user sessions across different platforms.

    A session represents a chat window for a specific user on a specific platform.
    Each session can have multiple conversations (对话) associated with it.
    """

    __tablename__: str = "platform_sessions"

    inner_id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    session_id: str = Field(
        max_length=100,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    platform_id: str = Field(default="webchat", nullable=False)
    """Platform identifier (e.g., 'webchat', 'qq', 'discord')"""
    creator: str = Field(nullable=False)
    """Username of the session creator"""
    display_name: str | None = Field(default=None, max_length=255)
    """Display name for the session"""
    is_group: int = Field(default=0, nullable=False)
    """0 for private chat, 1 for group chat (not implemented yet)"""

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            name="uix_platform_session_id",
        ),
    )


class UmoAlias(TimestampMixin, SQLModel, table=True):
    """User-facing names for unified message origins."""

    __tablename__: str = "umo_aliases"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    umo: str = Field(nullable=False, max_length=512, unique=True, index=True)
    creator_sender_id: str = Field(nullable=False, max_length=255)
    auto_name: str | None = Field(default=None, max_length=255)
    user_alias: str | None = Field(default=None, max_length=255)

    __table_args__ = (
        UniqueConstraint(
            "umo",
            name="uix_umo_alias_umo",
        ),
    )


class Attachment(TimestampMixin, SQLModel, table=True):
    """This class represents attachments for messages in AstrBot.

    Attachments can be images, files, or other media types.
    """

    __tablename__: str = "attachments"

    inner_attachment_id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
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

    __table_args__ = (
        UniqueConstraint(
            "attachment_id",
            name="uix_attachment_id",
        ),
    )


class ApiKey(TimestampMixin, SQLModel, table=True):
    """API keys used by external developers to access Open APIs."""

    __tablename__: str = "api_keys"

    inner_id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    key_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    name: str = Field(max_length=255, nullable=False)
    key_hash: str = Field(max_length=128, nullable=False, unique=True)
    key_prefix: str = Field(max_length=24, nullable=False)
    scopes: list | None = Field(default=None, sa_type=JSON)
    created_by: str = Field(max_length=255, nullable=False)
    last_used_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)
    revoked_at: datetime | None = Field(default=None)

    __table_args__ = (
        UniqueConstraint(
            "key_id",
            name="uix_api_key_id",
        ),
        UniqueConstraint(
            "key_hash",
            name="uix_api_key_hash",
        ),
    )


class DashboardAccount(TimestampMixin, SQLModel, table=True):
    """Stable Dashboard identity independent from a mutable username."""

    __tablename__ = "dashboard_accounts"  # type: ignore

    account_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    username: str = Field(nullable=False, unique=True, index=True, max_length=255)
    password_hash: str = Field(nullable=False, sa_type=Text)
    is_active: bool = Field(default=True, nullable=False, index=True)
    created_by: str | None = Field(default=None, index=True, max_length=512)
    last_login_at: datetime | None = Field(default=None, index=True)
    # TOTP belongs to this immutable account identity; a username rename must
    # never transfer a second factor to a different account.
    totp_enabled: bool = Field(default=False, nullable=False)
    totp_secret: str = Field(default="", nullable=False, sa_type=Text)
    totp_recovery_code_hash: str = Field(default="", nullable=False, sa_type=Text)


class AuthRoleBinding(TimestampMixin, SQLModel, table=True):
    """An explicit role binding. The authorization service enforces scope."""

    __tablename__ = "auth_role_bindings"  # type: ignore

    binding_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    subject_id: str = Field(nullable=False, index=True, max_length=512)
    role: str = Field(nullable=False, index=True, max_length=64)
    scope_type: str = Field(nullable=False, index=True, max_length=32)
    scope_id: str = Field(nullable=False, max_length=4096)
    config_id: str | None = Field(default=None, index=True, max_length=128)
    source: str = Field(nullable=False, default="explicit", max_length=64)
    expires_at: datetime | None = Field(default=None, index=True)
    created_by: str | None = Field(default=None, max_length=512)
    revoked_at: datetime | None = Field(default=None, index=True)
    revoked_by: str | None = Field(default=None, max_length=512)
    metadata_json: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "scope_type",
            "scope_id",
            "config_id",
            name="uix_auth_role_binding_scope",
        ),
        Index(
            "ix_auth_role_bindings_active_scope",
            "subject_id",
            "config_id",
            "revoked_at",
            "expires_at",
        ),
    )


class AuthPlatformMembershipFact(TimestampMixin, SQLModel, table=True):
    """Short-lived adapter role observation, never an explicit role binding."""

    __tablename__ = "auth_platform_membership_facts"  # type: ignore

    fact_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    subject_id: str = Field(nullable=False, index=True, max_length=512)
    config_id: str = Field(nullable=False, index=True, max_length=128)
    platform_instance: str = Field(nullable=False, index=True, max_length=255)
    umo: str = Field(nullable=False, max_length=2048)
    platform_role: str = Field(nullable=False, max_length=32)
    source: str = Field(nullable=False, max_length=32)
    observed_at: datetime = Field(nullable=False, index=True)
    expires_at: datetime = Field(nullable=False, index=True)
    metadata_json: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "config_id",
            "platform_instance",
            "umo",
            name="uix_auth_platform_fact_scope",
        ),
        Index(
            "ix_auth_platform_facts_active",
            "config_id",
            "umo",
            "subject_id",
            "expires_at",
        ),
    )


class AuthStepUpCredential(SQLModel, table=True):
    """One-time Dashboard proof. Only a secret hash is stored."""

    __tablename__ = "auth_step_up_credentials"  # type: ignore

    credential_id: str = Field(primary_key=True, max_length=64)
    subject_id: str = Field(nullable=False, index=True, max_length=512)
    dashboard_session_id: str = Field(nullable=False, index=True, max_length=512)
    action: str = Field(nullable=False, max_length=128)
    resource_id: str = Field(nullable=False, max_length=4096)
    context_digest: str = Field(nullable=False, max_length=128)
    token_hash: str = Field(nullable=False, max_length=128)
    verified_method: str = Field(nullable=False, max_length=32)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    expires_at: datetime = Field(nullable=False, index=True)
    consumed_at: datetime | None = Field(default=None, index=True)

    __table_args__ = (
        Index(
            "ix_auth_step_up_consume",
            "subject_id",
            "action",
            "resource_id",
            "expires_at",
            "consumed_at",
        ),
    )


class AuthAuditLog(SQLModel, table=True):
    """Append-only, redacted authorization decision history."""

    __tablename__ = "auth_audit_log"  # type: ignore

    audit_id: str = Field(primary_key=True, max_length=64)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    request_id: str | None = Field(default=None, index=True, max_length=128)
    subject_id: str = Field(nullable=False, index=True, max_length=512)
    effective_role: str | None = Field(default=None, max_length=64)
    source: str = Field(nullable=False, max_length=64)
    platform: str | None = Field(default=None, max_length=255)
    config_id: str | None = Field(default=None, index=True, max_length=128)
    action: str = Field(nullable=False, index=True, max_length=128)
    resource_id: str = Field(nullable=False, max_length=4096)
    decision: str = Field(nullable=False, index=True, max_length=32)
    reason: str = Field(nullable=False, max_length=128)
    step_up_id: str | None = Field(default=None, index=True, max_length=64)
    outcome: str | None = Field(default=None, max_length=64)
    latency_ms: int | None = Field(default=None)
    metadata_json: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (
        Index(
            "ix_auth_audit_config_action_timestamp", "config_id", "action", "timestamp"
        ),
    )


class AuthPolicyOverride(TimestampMixin, SQLModel, table=True):
    """A structured allow-list override for a fixed action and narrow scope."""

    __tablename__ = "auth_policy_overrides"  # type: ignore

    override_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True
    )
    action: str = Field(nullable=False, index=True, max_length=128)
    resource_type: str = Field(nullable=False, max_length=64)
    resource_id: str | None = Field(default=None, max_length=4096)
    config_id: str | None = Field(default=None, index=True, max_length=128)
    allowed_roles: list = Field(default_factory=list, sa_type=JSON)
    enabled: bool = Field(default=True, nullable=False, index=True)
    expires_at: datetime | None = Field(default=None, index=True)
    created_by: str | None = Field(default=None, max_length=512)
    metadata_json: dict = Field(default_factory=dict, sa_type=JSON)


class DashboardTrustedDevice(TimestampMixin, SQLModel, table=True):
    """Trusted dashboard device token used to skip TOTP for a limited time."""

    __tablename__: str = "dashboard_trusted_devices"

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    token_hash: str = Field(max_length=64, nullable=False, unique=True, index=True)
    account_id: str = Field(nullable=False, index=True, max_length=64)
    totp_secret_hash: str = Field(max_length=64, nullable=False, index=True)
    expires_at: datetime = Field(nullable=False, index=True)


class ChatUIProject(TimestampMixin, SQLModel, table=True):
    """This class represents projects for organizing ChatUI conversations.

    Projects allow users to group related conversations together.
    """

    __tablename__: str = "chatui_projects"

    inner_id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    project_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    creator: str = Field(nullable=False)
    """Username of the project creator"""
    emoji: str | None = Field(default="📁", max_length=10)
    """Emoji icon for the project"""
    title: str = Field(nullable=False, max_length=255)
    """Title of the project"""
    description: str | None = Field(default=None, max_length=1000)
    """Description of the project"""

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            name="uix_chatui_project_id",
        ),
    )


class SessionProjectRelation(SQLModel, table=True):
    """This class represents the relationship between platform sessions and ChatUI projects."""

    __tablename__: str = "session_project_relations"

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    session_id: str = Field(nullable=False, max_length=100)
    """Session ID from PlatformSession"""
    project_id: str = Field(nullable=False, max_length=36)
    """Project ID from ChatUIProject"""

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            name="uix_session_project_relation",
        ),
    )


class CommandConfig(TimestampMixin, SQLModel, table=True):
    """Per-command configuration overrides for dashboard management."""

    __tablename__ = "command_configs"  # type: ignore

    handler_full_name: str = Field(
        primary_key=True,
        max_length=512,
    )
    plugin_name: str = Field(nullable=False, max_length=255)
    module_path: str = Field(nullable=False, max_length=255)
    original_command: str = Field(nullable=False, max_length=255)
    resolved_command: str | None = Field(default=None, max_length=255)
    enabled: bool = Field(default=True, nullable=False)
    keep_original_alias: bool = Field(default=False, nullable=False)
    conflict_key: str | None = Field(default=None, max_length=255)
    resolution_strategy: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, sa_type=Text)
    extra_data: dict | None = Field(default=None, sa_type=JSON)
    auto_managed: bool = Field(default=False, nullable=False)


class CommandConflict(TimestampMixin, SQLModel, table=True):
    """Conflict tracking for duplicated command names."""

    __tablename__ = "command_conflicts"  # type: ignore

    id: int | None = Field(
        default=None, primary_key=True, sa_column_kwargs={"autoincrement": True}
    )
    conflict_key: str = Field(nullable=False, max_length=255)
    handler_full_name: str = Field(nullable=False, max_length=512)
    plugin_name: str = Field(nullable=False, max_length=255)
    status: str = Field(default="pending", max_length=32)
    resolution: str | None = Field(default=None, max_length=64)
    resolved_command: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, sa_type=Text)
    extra_data: dict | None = Field(default=None, sa_type=JSON)
    auto_generated: bool = Field(default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "conflict_key",
            "handler_full_name",
            name="uix_conflict_handler",
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
    token_usage: int = 0
    """对话的总 token 数量。AstrBot 会保留最近一次 LLM 请求返回的总 token 数，方便统计。token_usage 可能为 0，表示未知。"""


class Personality(TypedDict):
    """LLM 人格类。

    在 v4.0.0 版本及之后，推荐使用上面的 Persona 类。
    """

    prompt: str
    name: str
    begin_dialogs: list[str]
    tools: list[str] | None
    """工具列表。None 表示使用所有工具，空列表表示不使用任何工具"""
    skills: list[str] | None
    """Skills 列表。None 表示使用所有 Skills，空列表表示不使用任何 Skills"""
    custom_error_message: str | None
    """可选的人格自定义报错回复信息。配置后将优先发送给最终用户。"""

    # cache
    _begin_dialogs_processed: list[dict]
