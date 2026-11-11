"""Wallet credit / debit helpers for fish customer balances."""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.wallet import WalletAccount
from app.schemas.commerce import WalletPublic
from app.services.rice import rice_grams_from_internal

logger = logging.getLogger(__name__)


def settle_arrears_from_balance(wallet: WalletAccount) -> None:
    """Use bowl balance to pay down arrears (same rule as top-up)."""
    if wallet.arrears_yuan <= 0 or wallet.balance_yuan <= 0:
        return
    pay_debt = min(wallet.arrears_yuan, wallet.balance_yuan)
    wallet.arrears_yuan = (wallet.arrears_yuan - pay_debt).quantize(Decimal("0.0001"))
    wallet.balance_yuan = (wallet.balance_yuan - pay_debt).quantize(Decimal("0.0001"))


def get_or_create_wallet(db: Session, user_id: str) -> WalletAccount:
    """Fetch or initialize a wallet row for the user."""
    wallet = db.get(WalletAccount, user_id)
    if wallet is None:
        wallet = WalletAccount(user_id=user_id)
        db.add(wallet)
        db.flush()
    return wallet


def apply_topup(db: Session, user: User, pay_yuan: Decimal) -> WalletAccount:
    """Credit wallet after payment: ratio, then arrears, then balance."""
    wallet = get_or_create_wallet(db, user.id)
    ratio = Decimal(str(settings.topup_credit_ratio))
    credit = (pay_yuan * ratio).quantize(Decimal("0.0001"))
    if wallet.arrears_yuan > 0:
        pay_debt = min(credit, wallet.arrears_yuan)
        wallet.arrears_yuan = (wallet.arrears_yuan - pay_debt).quantize(
            Decimal("0.0001")
        )
        credit -= pay_debt
    wallet.balance_yuan = (wallet.balance_yuan + credit).quantize(Decimal("0.0001"))
    user.paid = True
    db.add(wallet)
    db.add(user)
    db.flush()
    from app.services.usage_billing import enforce_bot_for_wallet

    enforce_bot_for_wallet(db, user, enable_if_active=True)
    return wallet


def customer_wallet_public(wallet: WalletAccount, user: User) -> WalletPublic:
    """Map internal APIKEY balance to 白饭（1 实付元 = 500g，经 ratio 从内部还原）。"""
    _ = user
    bal = wallet.balance_yuan.quantize(Decimal("0.01"))
    arr = wallet.arrears_yuan.quantize(Decimal("0.01"))
    return WalletPublic(
        balance_yuan=bal,
        balance_rice_g=rice_grams_from_internal(wallet.balance_yuan),
        arrears_yuan=arr,
        arrears_rice_g=rice_grams_from_internal(wallet.arrears_yuan),
        status=wallet.status,
        can_bind=wallet.balance_yuan > 0 and wallet.status == "active",
    )
