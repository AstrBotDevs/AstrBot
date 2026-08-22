import uuid
from datetime import datetime

from sqlmodel import JSON, Field, SQLModel, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


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
