import math
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.engine import get_db
from app.models.order import TopupOrder
from app.models.user import User
from app.schemas.commerce import CreateOrderRequest, OrderPublic
from app.services.memo_code import build_memo_code, require_integer_yuan
from app.services.wallet import apply_topup

router = APIRouter(prefix="/orders", tags=["orders"])

_MEMO_ALLOCATE_ATTEMPTS = 32


def _allocate_unique_memo(db: Session, yuan: int) -> str:
    """Pick a memo_code not used by any existing order."""
    for _ in range(_MEMO_ALLOCATE_ATTEMPTS):
        code = build_memo_code(yuan)
        taken = db.scalar(
            select(TopupOrder.id).where(TopupOrder.memo_code == code).limit(1)
        )
        if taken is None:
            return code
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="备注码生成失败，请稍后再试",
    )


@router.get("/me", response_model=list[OrderPublic])
def list_my_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TopupOrder]:
    """List current user's top-up orders newest first."""
    rows = db.scalars(
        select(TopupOrder)
        .where(TopupOrder.user_id == current_user.id)
        .order_by(TopupOrder.created_at.desc())
        .limit(50)
    ).all()
    return list(rows)


@router.post("", response_model=OrderPublic, status_code=status.HTTP_201_CREATED)
def create_order(
    body: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TopupOrder:
    """Create a pending Alipay top-up order."""
    try:
        yuan = require_integer_yuan(Decimal(body.amount_yuan))
    except ValueError as exc:
        if str(exc) == "integer_yuan_only":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="添饭只支持整数元，不能有小数",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="金额不合法",
        ) from exc
    min_yuan = math.ceil(settings.min_topup_yuan)
    if yuan < min_yuan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"最少添饭 ¥{min_yuan}",
        )
    amount = Decimal(yuan)
    memo_code = _allocate_unique_memo(db, yuan)
    order = TopupOrder(
        user_id=current_user.id,
        amount_yuan=amount,
        memo_code=memo_code,
        plan_id=body.plan_id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/mark-paid", response_model=OrderPublic)
def mark_order_paid(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TopupOrder:
    """Customer marks that Alipay transfer was completed."""
    order = db.scalar(
        select(TopupOrder).where(
            TopupOrder.id == order_id,
            TopupOrder.user_id == current_user.id,
        )
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    if order.status == "confirmed":
        return order
    order.status = "user_marked"
    db.add(order)
    db.commit()
    db.refresh(order)
    if settings.auto_confirm_orders:
        return _confirm_order(db, order)
    return order


@router.post("/{order_id}/confirm", response_model=OrderPublic)
def confirm_order_admin(
    order_id: str,
    x_fish_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> TopupOrder:
    """Operator confirms payment and credits wallet (requires admin key)."""
    if not settings.admin_api_key or x_fish_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    order = db.get(TopupOrder, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    return _confirm_order(db, order)


def _confirm_order(db: Session, order: TopupOrder) -> TopupOrder:
    if order.status == "confirmed":
        return order
    user = db.get(User, order.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    apply_topup(db, user, order.amount_yuan)
    order.status = "confirmed"
    order.confirmed_at = datetime.now(UTC)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order
