"""User models for fastapi-users authentication."""

import uuid

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlmodel import SQLModel


class User(SQLAlchemyBaseUserTableUUID):
    """User model for authentication with fastapi-users.

    This model extends SQLAlchemyBaseUserTableUUID which provides:
    - id: UUID primary key
    - email: str
    - hashed_password: str
    - is_active: bool
    - is_superuser: bool
    - is_verified: bool
    """

    # The base class provides these fields automatically:
    # id: uuid.UUID
    # email: str
    # hashed_password: str
    # is_active: bool = True
    # is_superuser: bool = False
    # is_verified: bool = False

    __tablename__ = "user"


class UserRead(SQLModel):
    """Schema for reading user data."""

    id: uuid.UUID
    email: str
    username: str
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False


class UserCreate(SQLModel):
    """Schema for creating a new user."""

    email: str
    username: str
    password: str


class UserUpdate(SQLModel):
    """Schema for updating user data."""

    email: str | None = None
    username: str | None = None
    password: str | None = None
