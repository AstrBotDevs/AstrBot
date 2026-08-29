from sqlmodel import JSON, Field, SQLModel, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


class Preference(TimestampMixin, SQLModel, table=True):
    """This class represents preferences for bots."""

    __tablename__ = "preferences"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    scope: str = Field(nullable=False)
    """Scope of the preference, such as 'global', 'umo', 'plugin'."""
    scope_id: str = Field(nullable=False)
    """ID of the scope, such as 'global', 'umo', 'plugin_name'."""
    key: str = Field(nullable=False)
    value: dict = Field(sa_type=JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "scope",
            "scope_id",
            "key",
            name="uix_preference_scope_scope_id_key",
        ),
    )
