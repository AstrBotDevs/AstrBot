from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.ticket import SupportTicket
from app.models.user import User
from app.schemas.commerce import TicketCreateRequest, TicketPublic

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("/me", response_model=list[TicketPublic])
def list_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SupportTicket]:
    """List support tickets for the current user."""
    return list(
        db.scalars(
            select(SupportTicket)
            .where(SupportTicket.user_id == current_user.id)
            .order_by(SupportTicket.created_at.desc())
            .limit(30)
        ).all()
    )


@router.post("", response_model=TicketPublic, status_code=status.HTTP_201_CREATED)
def create_ticket(
    body: TicketCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SupportTicket:
    """Open a support ticket to fish staff."""
    ticket = SupportTicket(
        user_id=current_user.id,
        subject=body.subject.strip(),
        body=body.body.strip(),
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket
