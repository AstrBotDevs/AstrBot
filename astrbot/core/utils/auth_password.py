"""Utilities for dashboard password hashing and verification."""

import hashlib
import hmac
import re
import secrets
import string

_PBKDF2_ITERATIONS = 600_000
_PBKDF2_SALT_BYTES = 16
_PBKDF2_ALGORITHM = "pbkdf2_sha256"
_PBKDF2_FORMAT = f"{_PBKDF2_ALGORITHM}$"
_LEGACY_MD5_LENGTH = 32
_DASHBOARD_PASSWORD_MIN_LENGTH = 8
_GENERATED_DASHBOARD_PASSWORD_LENGTH = 24
DEFAULT_DASHBOARD_PASSWORD = "astrbot"


def generate_dashboard_password() -> str:
    """Generate a strong dashboard password that satisfies the complexity policy."""
    alphabet = string.ascii_letters + string.digits
    password_chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        *(
            secrets.choice(alphabet)
            for _ in range(_GENERATED_DASHBOARD_PASSWORD_LENGTH - 3)
        ),
    ]
    secrets.SystemRandom().shuffle(password_chars)
    return "".join(password_chars)


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


def hash_legacy_dashboard_password(raw_password: str) -> str:
    """Return legacy MD5 hash for downgrade compatibility only."""
    if not isinstance(raw_password, str) or raw_password == "":
        raise ValueError("Password cannot be empty")
    return hashlib.md5(raw_password.encode("utf-8")).hexdigest()


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
        # Keep compatibility with existing MD5-based deployments while requiring
        # the real plaintext password, not the stored MD5 value itself.
        candidate_md5 = hashlib.md5(candidate_password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(stored_hash.lower(), candidate_md5.lower())

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
