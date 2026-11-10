from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    """Hash a plaintext password for storage.

    Args:
        plain: User-provided password.

    Returns:
        Bcrypt hash string.
    """
    digest = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())
    return digest.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    """Create a signed JWT for the given subject (user id as string).

    Args:
        subject: Unique user identifier.
        extra: Optional additional JWT claims.

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "iat": now}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Raises:
        jwt.PyJWTError: When the token is invalid or expired.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
