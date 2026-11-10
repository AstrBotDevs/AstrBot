from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.api.orders import _confirm_order
from app.core.config import settings
from app.db.engine import get_db
from app.models.order import TopupOrder
from app.models.user import User
from app.schemas.commerce import AdminOrderPublic, OrderPublic

router = APIRouter(prefix="/admin", tags=["admin"])


def _credit_for_order(amount_yuan: Decimal) -> Decimal:
    ratio = Decimal(str(settings.topup_credit_ratio))
    return (amount_yuan * ratio).quantize(Decimal("0.0001"))


@router.get("/orders", response_model=list[AdminOrderPublic])
def list_orders_for_admin(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[AdminOrderPublic]:
    """List top-up orders across users (newest first)."""
    stmt = (
        select(TopupOrder, User.email)
        .join(User, User.id == TopupOrder.user_id)
        .order_by(TopupOrder.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(TopupOrder.status == status_filter)
    rows = db.execute(stmt).all()
    return [
        AdminOrderPublic(
            id=order.id,
            amount_yuan=order.amount_yuan,
            status=order.status,
            pay_channel=order.pay_channel,
            memo_code=order.memo_code,
            plan_id=order.plan_id,
            created_at=order.created_at,
            user_email=email,
            credit_yuan=_credit_for_order(order.amount_yuan),
        )
        for order, email in rows
    ]


@router.post("/orders/{order_id}/confirm", response_model=OrderPublic)
def confirm_order_as_admin(
    order_id: str,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> TopupOrder:
    """Credit wallet after operator verified Alipay transfer."""
    order = db.get(TopupOrder, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    return _confirm_order(db, order)
