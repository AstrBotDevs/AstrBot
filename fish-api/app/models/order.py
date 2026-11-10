import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.engine import Base


class TopupOrder(Base):
    """Manual Alipay (or other) top-up awaiting operator confirmation."""

    __tablename__ = "topup_orders"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    amount_yuan: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    # pending | user_marked | confirmed | rejected
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    pay_channel: Mapped[str] = mapped_column(
        String(32), default="alipay", nullable=False
    )
    memo_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
