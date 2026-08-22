import uuid

from sqlmodel import Field, SQLModel, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


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
