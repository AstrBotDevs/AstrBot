from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.user import User
from app.models.wallet import BotBinding
from app.schemas.commerce import BindingPublic, ProfilePublic
from app.services.usage_billing import enforce_bot_for_wallet, sync_usage_charges
from app.services.wallet import customer_wallet_public

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=ProfilePublic)
def profile_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfilePublic:
    """Email, wallet, and binding snapshot."""
    wallet = sync_usage_charges(db, current_user)
    enforce_bot_for_wallet(db, current_user, enable_if_active=True)
    db.commit()
    db.refresh(wallet)
    binding = db.scalar(select(BotBinding).where(BotBinding.user_id == current_user.id))
    return ProfilePublic(
        email=current_user.email,
        paid=current_user.paid,
        wallet=customer_wallet_public(wallet, current_user),
        binding=BindingPublic.model_validate(binding) if binding else None,
    )
