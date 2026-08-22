from datetime import datetime

from sqlmodel import Field, SQLModel, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


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
