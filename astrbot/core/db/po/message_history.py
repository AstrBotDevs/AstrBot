from sqlmodel import JSON, Field, Index, SQLModel

from astrbot.core.db.po.mixins import TimestampMixin


class PlatformMessageHistory(TimestampMixin, SQLModel, table=True):
    """This class represents the message history for a specific platform.

    It is used to store messages that are not LLM-generated, such as user messages
    or platform-specific messages.
    """

    __tablename__ = "platform_message_history"  # type: ignore

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
