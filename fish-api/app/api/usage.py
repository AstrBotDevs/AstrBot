from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.user import User
from app.schemas.commerce import UsageRow, UsageSummary
from app.services.usage import get_binding_or_none, query_usage_rows

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/me", response_model=UsageSummary)
def usage_me(
    days: int = Query(default=7, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UsageSummary:
    """Token usage for the bound bot (display multiplier applied server-side)."""
    binding = get_binding_or_none(db, current_user.id)
    if binding is None:
        return UsageSummary(days=days, rows=[], total_rice_g=0, bound=False)
    rows_raw = query_usage_rows(binding.umo_prefix, days=days)
    rows = [UsageRow.model_validate(item) for item in rows_raw]
    total = sum(r.rice_g for r in rows)
    return UsageSummary(days=days, rows=rows, total_rice_g=total, bound=True)
