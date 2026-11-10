from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.user import User
from app.models.wallet import BotBinding
from app.schemas.commerce import BindingPublic, ProfilePublic
from app.services.wallet import customer_wallet_public, get_or_create_wallet

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=ProfilePublic)
def profile_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfilePublic:
    """Email, wallet, and binding snapshot."""
    wallet = get_or_create_wallet(db, current_user.id)
    db.commit()
    binding = db.scalar(select(BotBinding).where(BotBinding.user_id == current_user.id))
    return ProfilePublic(
        email=current_user.email,
        paid=current_user.paid,
        wallet=customer_wallet_public(wallet, current_user),
        binding=BindingPublic.model_validate(binding) if binding else None,
    )
