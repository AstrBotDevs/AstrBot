"""Utilities for dashboard password hashing and verification."""

import hashlib
import hmac
import re
import secrets

_PBKDF2_ITERATIONS = 600_000
_PBKDF2_SALT_BYTES = 16
_PBKDF2_ALGORITHM = "pbkdf2_sha256"
_PBKDF2_FORMAT = f"{_PBKDF2_ALGORITHM}$"
_LEGACY_MD5_LENGTH = 32
_DASHBOARD_PASSWORD_MIN_LENGTH = 12
DEFAULT_DASHBOARD_PASSWORD = "astrbot"


def hash_dashboard_password(raw_password: str) -> str:
    """Return a salted hash for dashboard password using PBKDF2-HMAC-SHA256."""
    if not isinstance(raw_password, str) or raw_password == "":
        raise ValueError("Password cannot be empty")

    salt = secrets.token_hex(_PBKDF2_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        bytes.fromhex(salt),
        _PBKDF2_ITERATIONS,
    ).hex()
    return f"{_PBKDF2_FORMAT}{_PBKDF2_ITERATIONS}${salt}${digest}"


def validate_dashboard_password(raw_password: str) -> None:
    """Validate whether dashboard password meets the minimal complexity policy."""
    if not isinstance(raw_password, str) or raw_password == "":
        raise ValueError("Password cannot be empty")
    if len(raw_password) < _DASHBOARD_PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Password must be at least {_DASHBOARD_PASSWORD_MIN_LENGTH} characters long"
        )

    if not re.search(r"[A-Z]", raw_password):
        raise ValueError("Password must include at least one uppercase letter")
    if not re.search(r"[a-z]", raw_password):
        raise ValueError("Password must include at least one lowercase letter")
    if not re.search(r"\d", raw_password):
        raise ValueError("Password must include at least one digit")


def normalize_dashboard_password_hash(stored_password: str) -> str:
    """Ensure dashboard password has a value, fallback to default dashboard password hash."""
    if not stored_password:
        return hash_dashboard_password(DEFAULT_DASHBOARD_PASSWORD)
    return stored_password


def _is_legacy_md5_hash(stored: str) -> bool:
    return (
        isinstance(stored, str)
        and len(stored) == _LEGACY_MD5_LENGTH
        and all(c in "0123456789abcdefABCDEF" for c in stored)
    )


def _is_pbkdf2_hash(stored: str) -> bool:
    return isinstance(stored, str) and stored.startswith(_PBKDF2_FORMAT)


def verify_dashboard_password(stored_hash: str, candidate_password: str) -> bool:
    """Verify password against legacy md5 or new PBKDF2-SHA256 format."""
    if not isinstance(stored_hash, str) or not isinstance(candidate_password, str):
        return False

    if _is_legacy_md5_hash(stored_hash):
        # Keep compatibility with existing md5-based deployments:
        # new clients send plain password, old clients may send md5 of it.
        candidate_md5 = hashlib.md5(candidate_password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(
            stored_hash.lower(), candidate_md5.lower()
        ) or hmac.compare_digest(
            stored_hash.lower(),
            candidate_password.lower(),
        )

    if _is_pbkdf2_hash(stored_hash):
        parts: list[str] = stored_hash.split("$")
        if len(parts) != 4:
            return False
        _, iterations_s, salt, digest = parts
        try:
            iterations = int(iterations_s)
            stored_key = bytes.fromhex(digest)
            salt_bytes = bytes.fromhex(salt)
        except (TypeError, ValueError):
            return False
        candidate_key = hashlib.pbkdf2_hmac(
            "sha256",
            candidate_password.encode("utf-8"),
            salt_bytes,
            iterations,
        )
        return hmac.compare_digest(stored_key, candidate_key)

    return False


def is_default_dashboard_password(stored_hash: str) -> bool:
    """Check whether the password still equals the built-in default value."""
    return verify_dashboard_password(stored_hash, DEFAULT_DASHBOARD_PASSWORD)


def is_legacy_dashboard_password(stored_hash: str) -> bool:
    """Check whether the password is still stored with legacy MD5."""
    return _is_legacy_md5_hash(stored_hash)
