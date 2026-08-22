import uuid
from datetime import UTC, datetime

from sqlmodel import JSON, Field, SQLModel, Text, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


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
