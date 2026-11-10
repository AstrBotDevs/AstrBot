from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.engine import get_db
from app.models.user import User
from app.services.admin_policy import resolve_role_for_email, sync_user_role
from app.services.email_guard import assert_registration_email_ok
from app.services.wallet import get_or_create_wallet
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserPublic,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_response(user: User) -> AuthResponse:
    token = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        user=UserPublic.model_validate(user),
    )


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Register a new user and return an access token."""
    email = body.email.lower()
    assert_registration_email_ok(email)
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        paid=False,
        role=resolve_role_for_email(email),
    )
    db.add(user)
    try:
        db.flush()
        get_or_create_wallet(db, user.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc
    db.refresh(user)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Authenticate with email and password."""
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    sync_user_role(user)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _auth_response(user)


@router.get("/me", response_model=UserPublic)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPublic:
    """Return the currently authenticated user."""
    sync_user_role(current_user)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return UserPublic.model_validate(current_user)
