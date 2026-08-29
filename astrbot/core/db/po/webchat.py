import uuid

from sqlmodel import Field, SQLModel, Text, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


class WebChatThread(TimestampMixin, SQLModel, table=True):
    """A side thread created from a selected WebChat assistant response."""

    __tablename__ = "webchat_threads"  # type: ignore

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
