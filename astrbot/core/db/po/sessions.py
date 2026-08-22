import uuid

from sqlmodel import Field, SQLModel, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


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
