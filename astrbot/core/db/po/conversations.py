import uuid

from sqlmodel import JSON, Field, SQLModel, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


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
