"""User models for fastapi-users authentication."""

import uuid
from typing import Optional

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlmodel import Field, SQLModel


class User(SQLAlchemyBaseUserTableUUID, SQLModel, table=True):
    """User model for authentication with fastapi-users.
    
    This model extends SQLAlchemyBaseUserTableUUID which provides:
    - id: UUID primary key
    - email: str
    - hashed_password: str
    - is_active: bool
    - is_superuser: bool
    - is_verified: bool
    """
    __tablename__ = "users"
    
    # The base class provides these fields automatically:
    # id: uuid.UUID
    # email: str
    # hashed_password: str
    # is_active: bool = True
    # is_superuser: bool = False
    # is_verified: bool = False
    
    # Add custom fields
    username: str = Field(nullable=False, unique=True, max_length=255)


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
    email: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
