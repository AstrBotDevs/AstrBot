import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.engine import Base


class WalletAccount(Base):
    """Per-user balance and arrears (fish-api ledger)."""

    __tablename__ = "wallet_accounts"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    balance_yuan: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        default=Decimal("0"),
        nullable=False,
    )
    arrears_yuan: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        default=Decimal("0"),
        nullable=False,
    )
    # active | suspended_arrears | suspended_manual
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class BotBinding(Base):
    """Maps a fish user to an AstrBot platform adapter / umo prefix."""

    __tablename__ = "bot_bindings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    adapter_id: Mapped[str] = mapped_column(String(128), nullable=False)
    umo_prefix: Mapped[str] = mapped_column(String(256), nullable=False)
    qq_appid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bind_status: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False
    )
