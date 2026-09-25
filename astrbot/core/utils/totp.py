from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
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
_TOTP_ROTATION_TTL_SECONDS = 300


@dataclass
class _TotpRotationState:
    expires_at: float
    verified: bool = False
    pending_secret: str | None = None


_totp_rotation_states: dict[str, _TotpRotationState] = {}


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
        now = datetime.datetime.now(datetime.timezone.utc)
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
    config,
    code: str,
    include_pending: bool = False,
    allow_recovery: bool = False,
    *,
    session_id: str | None = None,
    pending_secret: str | None = None,
) -> TwoFactorCodeType | None:
    """Return a 2FA code type when a configured code is valid.

    Args:
        config: Current dashboard configuration.
        code: Code to verify and consume.
        include_pending: Whether to check this session's pending rotation.
        allow_recovery: Whether recovery codes are permitted.
        session_id: Unique identifier from the authenticated dashboard JWT.
        pending_secret: New secret submitted with the configuration being saved.

    Returns:
        The verified code type, or None when verification fails.
    """
    if not isinstance(code, str) or not code.strip():
        return None
    if await consume_configured_totp_code(config, code):
        return TwoFactorCodeType.TOTP
    if include_pending:
        state = _get_rotation_state(session_id)
        if (
            state is not None
            and state.pending_secret
            and state.pending_secret == pending_secret
            and await consume_totp_code(state.pending_secret, code)
        ):
            return TwoFactorCodeType.TOTP
    if allow_recovery and verify_recovery_code(config, code):
        return TwoFactorCodeType.RECOVERY
    return None


def _get_rotation_state(session_id: str | None) -> _TotpRotationState | None:
    """Discard expired rotations and look up the authenticated session.

    Args:
        session_id: Unique identifier from the authenticated dashboard JWT.

    Returns:
        The session's unexpired rotation state, if present.
    """
    now = time.monotonic()
    for key, state in list(_totp_rotation_states.items()):
        if state.expires_at <= now:
            del _totp_rotation_states[key]
    return _totp_rotation_states.get(session_id) if session_id else None


def set_pending_totp_secret(
    secret: str | None, *, session_id: str | None = None
) -> None:
    """Store a pending secret, or clear only this session's rotation.

    Args:
        secret: Verified new secret, or None after a successful config save.
        session_id: Unique identifier from the authenticated dashboard JWT.
    """
    state = _get_rotation_state(session_id)
    if not session_id:
        return
    if secret is None:
        _totp_rotation_states.pop(session_id, None)
    elif state is not None:
        state.pending_secret = secret


def set_rotation_verified(value: bool, *, session_id: str | None = None) -> None:
    """Set or clear this session's short-lived rotation authorization.

    Args:
        value: Whether the current TOTP was successfully verified.
        session_id: Unique identifier from the authenticated dashboard JWT.
    """
    _get_rotation_state(session_id)
    if not session_id:
        return
    if value:
        _totp_rotation_states[session_id] = _TotpRotationState(
            expires_at=time.monotonic() + _TOTP_ROTATION_TTL_SECONDS,
            verified=True,
        )
    else:
        _totp_rotation_states.pop(session_id, None)


def consume_rotation_verified(*, session_id: str | None = None) -> bool:
    """Consume this session's rotation authorization once, without extending it.

    Args:
        session_id: Unique identifier from the authenticated dashboard JWT.

    Returns:
        Whether an unexpired authorization was consumed.
    """
    state = _get_rotation_state(session_id)
    if state is not None and state.verified:
        state.verified = False
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
                > datetime.datetime.now(datetime.timezone.utc),
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

    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
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
                    <= datetime.datetime.now(datetime.timezone.utc)
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
