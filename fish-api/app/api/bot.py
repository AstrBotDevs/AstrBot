from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.user import User
from app.models.wallet import BotBinding
from app.schemas.commerce import BindingPublic, BindingUpsertRequest
from app.services.wallet import get_or_create_wallet

router = APIRouter(prefix="/bot", tags=["bot"])


def _can_bind(user: User, db: Session) -> bool:
    wallet = get_or_create_wallet(db, user.id)
    return wallet.balance_yuan > 0 or user.paid


@router.get("/binding", response_model=BindingPublic | None)
def get_binding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BotBinding | None:
    """Return the user's bot binding."""
    return db.scalar(select(BotBinding).where(BotBinding.user_id == current_user.id))


@router.put("/binding", response_model=BindingPublic)
def upsert_binding(
    body: BindingUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BotBinding:
    """Save QQ appid and platform ids for usage filtering and ops."""
    if not _can_bind(current_user, db):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Top up before binding",
        )
    umo_prefix = (body.umo_prefix or body.adapter_id).strip()
    adapter_id = body.adapter_id.strip()
    binding = db.scalar(select(BotBinding).where(BotBinding.user_id == current_user.id))
    if binding is None:
        binding = BotBinding(
            user_id=current_user.id,
            qq_appid=body.qq_appid.strip(),
            adapter_id=adapter_id,
            umo_prefix=umo_prefix,
            bind_status="pending",
        )
        db.add(binding)
    else:
        binding.qq_appid = body.qq_appid.strip()
        binding.adapter_id = adapter_id
        binding.umo_prefix = umo_prefix
        binding.bind_status = "pending"
    db.commit()
    db.refresh(binding)
    return binding
