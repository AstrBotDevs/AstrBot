from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import hmac
import secrets
from enum import Enum

import pyotp
from sqlmodel import col, delete, select

from astrbot.core.db.po import DashboardTrustedDevice

TOTP_TRUSTED_DEVICE_COOKIE_NAME = "astrbot_totp_trusted_device"
TOTP_TRUSTED_DEVICE_MAX_AGE = 30 * 24 * 60 * 60
RECOVERY_CODE_GROUP_COUNT = 4
RECOVERY_CODE_GROUP_LENGTH = 8
RECOVERY_CODE_LENGTH = RECOVERY_CODE_GROUP_COUNT * RECOVERY_CODE_GROUP_LENGTH
_RECOVERY_CODE_KDF_ITERATIONS = 600_000
_RECOVERY_CODE_KDF_SALT_BYTES = 16
_RECOVERY_CODE_KDF_ALGORITHM = "pbkdf2_sha256"

_last_totp_timecode: dict[str, int] = {}
_totp_replay_lock = asyncio.Lock()
_totp_pending_secret: str | None = (
    None  # pending new secret after rotation, before config save
)
_totp_rotation_verified: bool = (
    False  # user passed the current-TOTP verify step during rotation
)


class TwoFactorCodeType(Enum):
    TOTP = "totp"
    RECOVERY = "recovery"


def _get_totp_config(config) -> dict:
    totp_config = config.get("dashboard", {}).get("totp", {})
    return totp_config if isinstance(totp_config, dict) else {}


def is_totp_enabled(config) -> bool:
    """TOTP is fully configured and operational (enable + secret + recovery hash all present)."""
    totp_config = _get_totp_config(config)
    if not totp_config.get("enable", False):
        return False
    secret = totp_config.get("secret", "")
    if not isinstance(secret, str) or not secret.strip():
        return False
    recovery_code_hash = totp_config.get("recovery_code_hash", "")
    if not isinstance(recovery_code_hash, str) or not recovery_code_hash.strip():
        return False
    return True


def _get_verified_totp_timecode(secret: str, code: str) -> int | None:
    code = code.strip()
    try:
        totp = pyotp.TOTP(secret.strip())
        now = datetime.datetime.now(datetime.UTC)
        for offset in (-1, 0, 1):
            candidate_time = now + datetime.timedelta(seconds=offset * totp.interval)
            if hmac.compare_digest(str(totp.at(candidate_time)), code):
                return int(totp.timecode(candidate_time))
    except Exception:
        return None
    return None


async def consume_totp_code(secret: str, code: str) -> bool:
    global _last_totp_timecode
    timecode = _get_verified_totp_timecode(secret, code)
    if timecode is None:
        return False
    secret = secret.strip()
    async with _totp_replay_lock:
        if _last_totp_timecode.get(secret, -1) >= timecode:
            return False
        _last_totp_timecode[secret] = timecode
    return True


async def consume_configured_totp_code(config, code: str) -> bool:
    if not is_totp_enabled(config):
        return False
    secret = _get_totp_config(config).get("secret", "")
    return await consume_totp_code(secret, code)


async def verify_configured_2fa_code(
    config, code: str, include_pending: bool = False, allow_recovery: bool = False
) -> TwoFactorCodeType | None:
    """Return a 2FA code type when a configured code is valid.

    When include_pending is True, also checks the in-memory pending TOTP
    secret from an active rotation (used by config-save verification).
    When allow_recovery is False, only TOTP codes are accepted (recovery
    codes are rejected to prevent privilege escalation on sensitive ops).
    """
    if not isinstance(code, str) or not code.strip():
        return None
    if await consume_configured_totp_code(config, code):
        return TwoFactorCodeType.TOTP
    if include_pending:
        pending = _totp_pending_secret
        if pending and await consume_totp_code(pending, code):
            return TwoFactorCodeType.TOTP
    if allow_recovery and verify_recovery_code(config, code):
        return TwoFactorCodeType.RECOVERY
    return None


def set_pending_totp_secret(secret: str | None) -> None:
    """Set the pending TOTP secret for an in-memory rotation.

    After a successful TOTP rotation, the new secret is stored in memory
    so that the subsequent config save 2FA check can verify against it.
    Cleared once the config save completes.
    """
    global _totp_pending_secret
    _totp_pending_secret = secret


def set_rotation_verified(value: bool) -> None:
    """Set or clear the rotation-verified flag."""
    global _totp_rotation_verified
    _totp_rotation_verified = value


def consume_rotation_verified() -> bool:
    """Check and consume the rotation-verified flag (single-use).

    Returns True if the user has passed the old-key verification step.
    """
    global _totp_rotation_verified
    if _totp_rotation_verified:
        _totp_rotation_verified = False
        return True
    return False


def _hash_totp_trusted_device_token(config, token: str) -> str:
    jwt_secret = config["dashboard"].get("jwt_secret", "")
    if not isinstance(jwt_secret, str) or not jwt_secret:
        return ""
    return hmac.new(
        jwt_secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _hash_totp_secret(config) -> str:
    secret = _get_totp_config(config).get("secret", "")
    if not isinstance(secret, str) or not secret.strip():
        return ""
    return hashlib.sha256(secret.strip().encode("utf-8")).hexdigest()


async def is_totp_trusted_device_valid(config, db, cookie_token: str) -> bool:
    if not cookie_token:
        return False
    token_hash = _hash_totp_trusted_device_token(config, cookie_token)
    totp_secret_hash = _hash_totp_secret(config)
    if not token_hash or not totp_secret_hash:
        return False

    await _cleanup_expired_totp_trusted_devices(db)
    async with db.get_db() as session:
        result = await session.execute(
            select(DashboardTrustedDevice).where(
                col(DashboardTrustedDevice.token_hash) == token_hash,
                col(DashboardTrustedDevice.totp_secret_hash) == totp_secret_hash,
                col(DashboardTrustedDevice.expires_at)
                > datetime.datetime.now(datetime.UTC),
            )
        )
        return result.scalar_one_or_none() is not None


async def issue_totp_trusted_device(config, db) -> str | None:
    """Issue a trusted device token, save to DB, and return the raw token for cookie."""
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_totp_trusted_device_token(config, raw_token)
    totp_secret_hash = _hash_totp_secret(config)
    if not token_hash or not totp_secret_hash:
        return None

    expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        seconds=TOTP_TRUSTED_DEVICE_MAX_AGE
    )
    async with db.get_db() as session:
        async with session.begin():
            await session.execute(
                delete(DashboardTrustedDevice).where(
                    col(DashboardTrustedDevice.token_hash) == token_hash
                )
            )
            trusted_device = DashboardTrustedDevice.model_validate(
                {
                    "token_hash": token_hash,
                    "totp_secret_hash": totp_secret_hash,
                    "expires_at": expires_at,
                }
            )
            session.add(trusted_device)
    return raw_token


async def _cleanup_expired_totp_trusted_devices(db) -> None:
    async with db.get_db() as session:
        async with session.begin():
            await session.execute(
                delete(DashboardTrustedDevice).where(
                    col(DashboardTrustedDevice.expires_at)
                    <= datetime.datetime.now(datetime.UTC)
                )
            )


async def revoke_user_trusted_devices(db) -> None:
    async with db.get_db() as session:
        async with session.begin():
            await session.execute(delete(DashboardTrustedDevice))


def generate_recovery_code() -> tuple[str, str]:
    raw = secrets.token_bytes(20)
    recovery_code = base64.b32encode(raw).decode("ascii").rstrip("=")
    salt = secrets.token_hex(_RECOVERY_CODE_KDF_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        recovery_code.encode("utf-8"),
        bytes.fromhex(salt),
        _RECOVERY_CODE_KDF_ITERATIONS,
    ).hex()
    kdf_hash = f"{_RECOVERY_CODE_KDF_ALGORITHM}${_RECOVERY_CODE_KDF_ITERATIONS}${salt}${digest}"
    parts = [
        recovery_code[i : i + RECOVERY_CODE_GROUP_LENGTH]
        for i in range(0, len(recovery_code), RECOVERY_CODE_GROUP_LENGTH)
    ]
    return "-".join(parts), kdf_hash


def verify_recovery_code(config, code: str) -> bool:
    """Verify a recovery code against configured recovery_code_hash (PBKDF2)."""
    cleaned = "".join(char for char in code.upper() if char.isalnum())
    if len(cleaned) != RECOVERY_CODE_LENGTH:
        return False
    totp_config = _get_totp_config(config)
    stored_hash = totp_config.get("recovery_code_hash", "")
    if not isinstance(stored_hash, str) or not stored_hash:
        return False

    parts = stored_hash.split("$")
    if len(parts) != 4 or parts[0] != _RECOVERY_CODE_KDF_ALGORITHM:
        return False
    try:
        iterations = int(parts[1])
        salt = parts[2]
        expected_digest = parts[3]
    except (ValueError, IndexError):
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        cleaned.encode("utf-8"),
        bytes.fromhex(salt),
        iterations,
    ).hex()
    return hmac.compare_digest(candidate, expected_digest)
