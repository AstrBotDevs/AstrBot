import uuid

from sqlmodel import Field, SQLModel, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


class Attachment(TimestampMixin, SQLModel, table=True):
    """This class represents attachments for messages in AstrBot.

    Attachments can be images, files, or other media types.
    """

    __tablename__ = "attachments"  # type: ignore

    inner_attachment_id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    attachment_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    path: str = Field(nullable=False)  # Path to the file on disk
    type: str = Field(nullable=False)  # Type of the file (e.g., 'image', 'file')
    mime_type: str = Field(nullable=False)  # MIME type of the file

    __table_args__ = (
        UniqueConstraint(
            "attachment_id",
            name="uix_attachment_id",
        ),
    )
