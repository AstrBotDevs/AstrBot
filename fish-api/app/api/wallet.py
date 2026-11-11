
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.user import User
from app.schemas.commerce import WalletPublic
from app.services.usage_billing import enforce_bot_for_wallet, sync_usage_charges
from app.services.wallet import customer_wallet_public

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("/me", response_model=WalletPublic)
def wallet_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletPublic:
    """Return the customer's wallet balances (bills new usage first)."""
    wallet = sync_usage_charges(db, current_user)
    enforce_bot_for_wallet(db, current_user, enable_if_active=True)
    db.commit()
    db.refresh(wallet)
    return customer_wallet_public(wallet, current_user)
