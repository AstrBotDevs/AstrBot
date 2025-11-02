"""FastAPI-Users authentication configuration."""

import uuid
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from astrbot.core import logger
from astrbot.core.db.user import User


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """User manager for handling user operations."""
    
    reset_password_token_secret = None
    verification_token_secret = None
    
    def __init__(self, user_db: SQLAlchemyUserDatabase, jwt_secret: str):
        super().__init__(user_db)
        self.reset_password_token_secret = jwt_secret
        self.verification_token_secret = jwt_secret
    
    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """Called after a user registers."""
        logger.info(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Called after a user requests password reset."""
        logger.info(f"User {user.id} has forgot their password. Reset token: {token}")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Called after a user requests verification."""
        logger.info(f"Verification requested for user {user.id}. Verification token: {token}")


async def get_user_db(session: AsyncSession):
    """Dependency to get user database."""
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
    jwt_secret: str = Depends(lambda: None)
):
    """Dependency to get user manager."""
    yield UserManager(user_db, jwt_secret)


def get_jwt_strategy(jwt_secret: str) -> JWTStrategy:
    """Get JWT strategy with the provided secret."""
    return JWTStrategy(secret=jwt_secret, lifetime_seconds=7 * 24 * 60 * 60)  # 7 days


def get_auth_backend(jwt_secret: str) -> AuthenticationBackend:
    """Get authentication backend."""
    bearer_transport = BearerTransport(tokenUrl="api/auth/login")
    
    return AuthenticationBackend(
        name="jwt",
        transport=bearer_transport,
        get_strategy=lambda: get_jwt_strategy(jwt_secret),
    )


def setup_fastapi_users(jwt_secret: str) -> FastAPIUsers:
    """Setup FastAPI Users instance."""
    auth_backend = get_auth_backend(jwt_secret)
    
    # Note: get_user_manager will be passed when registering routes
    fastapi_users = FastAPIUsers[User, uuid.UUID](
        get_user_manager,
        [auth_backend],
    )
    
    return fastapi_users, auth_backend
