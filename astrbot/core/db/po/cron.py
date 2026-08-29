import uuid
from datetime import datetime

from sqlmodel import JSON, Field, SQLModel, Text

from astrbot.core.db.po.mixins import TimestampMixin


class CronJob(TimestampMixin, SQLModel, table=True):
    """Cron job definition for scheduler and WebUI management."""

    __tablename__ = "cron_jobs"  # type: ignore

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
