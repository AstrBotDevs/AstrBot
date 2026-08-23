from pydantic import model_validator
from sqlmodel import JSON, Field, SQLModel, Text, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


class CommandConfig(TimestampMixin, SQLModel, table=True):
    """Per-command configuration overrides for dashboard management."""

    __tablename__ = "command_configs"  # type: ignore

    handler_full_name: str = Field(
        primary_key=True,
        max_length=512,
    )
    command_id: str = Field(default="", nullable=False, max_length=512, unique=True)
    plugin_name: str = Field(nullable=False, max_length=255)
    module_path: str = Field(nullable=False, max_length=255)
    original_command: str = Field(nullable=False, max_length=255)
    resolved_command: str | None = Field(default=None, max_length=255)
    enabled: bool = Field(default=True, nullable=False)
    conflict_key: str | None = Field(default=None, max_length=255)
    resolution_strategy: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, sa_type=Text)
    extra_data: dict | None = Field(default=None, sa_type=JSON)
    auto_managed: bool = Field(default=False, nullable=False)

    @model_validator(mode="after")
    def _fill_command_id(self) -> CommandConfig:
        if not self.command_id:
            fragment = (self.original_command or "").replace(" ", ".")
            self.command_id = f"{self.plugin_name}:{fragment}"
        return self


class CommandConflict(TimestampMixin, SQLModel, table=True):
    """Conflict tracking for duplicated command names."""

    __tablename__ = "command_conflicts"  # type: ignore

    id: int | None = Field(
        default=None, primary_key=True, sa_column_kwargs={"autoincrement": True}
    )
    conflict_key: str = Field(nullable=False, max_length=255)
    handler_full_name: str = Field(nullable=False, max_length=512)
    command_id: str | None = Field(default=None, max_length=512)
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
