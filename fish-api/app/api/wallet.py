
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.user import User
from app.schemas.commerce import WalletPublic
from app.services.wallet import customer_wallet_public, get_or_create_wallet

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("/me", response_model=WalletPublic)
def wallet_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletPublic:
    """Return the customer's wallet balances."""
    wallet = get_or_create_wallet(db, current_user.id)
    db.commit()
    return customer_wallet_public(wallet, current_user)
