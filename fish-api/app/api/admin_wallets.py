"""Admin wallet adjustments for local QA."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.engine import get_db
from app.models.user import User
from app.models.wallet import BotBinding
from app.schemas.commerce import AdminWalletAdjustRequest, AdminWalletPublic
from app.services.rice import internal_yuan_from_display_rice_g, rice_grams_from_internal
from app.services.usage_billing import enforce_bot_for_wallet
from app.services.wallet import customer_wallet_public, get_or_create_wallet

router = APIRouter(prefix="/admin/wallets", tags=["admin"])


def _user_by_email(db: Session, email: str) -> User:
    normalized = email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == normalized))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


def _admin_wallet_public(db: Session, user: User) -> AdminWalletPublic:
    wallet = get_or_create_wallet(db, user.id)
    pub = customer_wallet_public(wallet, user)
    binding = db.scalar(select(BotBinding).where(BotBinding.user_id == user.id))
    return AdminWalletPublic(
        user_id=user.id,
        email=user.email,
        balance_yuan=pub.balance_yuan,
        balance_rice_g=pub.balance_rice_g,
        arrears_yuan=pub.arrears_yuan,
        arrears_rice_g=pub.arrears_rice_g,
        status=pub.status,
        adapter_id=binding.adapter_id if binding else None,
    )


@router.get("/by-email", response_model=AdminWalletPublic)
def get_wallet_by_email(
    email: str = Query(min_length=3),
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminWalletPublic:
    """Look up a customer's bowl (admin JWT required)."""
    user = _user_by_email(db, email)
    return _admin_wallet_public(db, user)


@router.post("/adjust", response_model=AdminWalletPublic)
def adjust_wallet(
    body: AdminWalletAdjustRequest,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminWalletPublic:
    """Set displayed rice grams for QA.

    Negative ``balance_rice_g`` is not kept on balance: it becomes 0g balance
    plus the absolute value as ``arrears_rice_g`` (欠饭).
    """
    user = _user_by_email(db, body.email)
    wallet = get_or_create_wallet(db, user.id)

    if body.balance_rice_g is not None:
        grams = int(body.balance_rice_g)
        if grams < 0:
            wallet.balance_yuan = Decimal("0.0000")
            wallet.arrears_yuan = (
                wallet.arrears_yuan + internal_yuan_from_display_rice_g(-grams)
            ).quantize(Decimal("0.0001"))
        else:
            wallet.balance_yuan = internal_yuan_from_display_rice_g(grams)

    if body.arrears_rice_g is not None:
        wallet.arrears_yuan = internal_yuan_from_display_rice_g(
            max(0, int(body.arrears_rice_g))
        )

    if wallet.balance_yuan <= 0:
        wallet.balance_yuan = Decimal("0.0000")
    if wallet.arrears_yuan < 0:
        wallet.arrears_yuan = Decimal("0.0000")

    _ = rice_grams_from_internal(wallet.balance_yuan)

    db.add(wallet)
    db.flush()

    if body.disable_bot_if_empty or body.enable_bot_if_active:
        enforce_bot_for_wallet(
            db,
            user,
            enable_if_active=body.enable_bot_if_active,
        )

    db.commit()
    db.refresh(wallet)
    return _admin_wallet_public(db, user)
