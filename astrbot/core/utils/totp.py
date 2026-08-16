import asyncio
import base64
import datetime
import hashlib
import hmac
import secrets
import time
from enum import Enum

import pyotp
from sqlmodel import col, delete, select

from astrbot.core.db.po import DashboardTrustedDevice
from astrbot.core.db.protocols import DatabaseSessionStore

TOTP_TRUSTED_DEVICE_COOKIE_NAME = "astrbot_totp_trusted_device"
TOTP_TRUSTED_DEVICE_MAX_AGE = 30 * 24 * 60 * 60
RECOVERY_CODE_GROUP_COUNT = 4
RECOVERY_CODE_GROUP_LENGTH = 8
RECOVERY_CODE_LENGTH = RECOVERY_CODE_GROUP_COUNT * RECOVERY_CODE_GROUP_LENGTH
_RECOVERY_CODE_KDF_ITERATIONS = 600_000
_RECOVERY_CODE_KDF_SALT_BYTES = 16
_RECOVERY_CODE_KDF_ALGORITHM = "pbkdf2_sha256"
_REPLAY_TIMECODE_RETENTION = 2
_MAX_REPLAY_ENTRIES = 4096
_ROTATION_STATE_TTL_SECONDS = 10 * 60


class TwoFactorCodeType(Enum):
    TOTP = "totp"
    RECOVERY = "recovery"


class TotpRuntimeState:
    """Runtime-owned mutable state for TOTP replay and rotation workflows.

    A dashboard process can have multiple authenticated sessions. Rotation state
    must therefore be scoped to the authenticated subject that started it,
    rather than living in a module-global slot shared by every runtime and
    request.
    """

    def __init__(self) -> None:
        self._last_totp_timecodes: dict[str, int] = {}
        self._replay_lock = asyncio.Lock()
        self._pending_secrets: dict[str, str] = {}
        self._rotation_verified_subjects: set[str] = set()
        self._rotation_expires_at: dict[str, float] = {}
        self._rotation_lock = asyncio.Lock()

    @staticmethod
    def _subject_key(subject: str) -> str:
        if not isinstance(subject, str) or not subject:
            raise ValueError("TOTP state requires an authenticated subject.")
        return subject

    @staticmethod
    def _secret_digest(secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def _cleanup_replay_timecodes(self, current_timecode: int) -> None:
        cutoff = current_timecode - _REPLAY_TIMECODE_RETENTION
        stale = [
            digest
            for digest, accepted_timecode in self._last_totp_timecodes.items()
            if accepted_timecode < cutoff
        ]
        for digest in stale:
            del self._last_totp_timecodes[digest]

        while len(self._last_totp_timecodes) > _MAX_REPLAY_ENTRIES:
            oldest_digest = min(
                self._last_totp_timecodes,
                key=self._last_totp_timecodes.__getitem__,
            )
            del self._last_totp_timecodes[oldest_digest]

    def _cleanup_expired_rotations(self) -> None:
        now = time.monotonic()
        expired_subjects = [
            subject
            for subject, expires_at in self._rotation_expires_at.items()
            if expires_at <= now
        ]
        for subject in expired_subjects:
            self._rotation_expires_at.pop(subject, None)
            self._pending_secrets.pop(subject, None)
            self._rotation_verified_subjects.discard(subject)

    def _touch_rotation(self, subject: str) -> None:
        self._rotation_expires_at[subject] = (
            time.monotonic() + _ROTATION_STATE_TTL_SECONDS
        )

    async def consume_totp_code(self, secret: str, code: str) -> bool:
        """Verify and atomically consume a TOTP code for this runtime."""
        timecode = _get_verified_totp_timecode(secret, code)
        if timecode is None:
            return False

        digest = self._secret_digest(secret.strip())
        async with self._replay_lock:
            self._cleanup_replay_timecodes(timecode)
            if self._last_totp_timecodes.get(digest, -1) >= timecode:
                return False
            self._last_totp_timecodes[digest] = timecode
        return True

    async def consume_configured_totp_code(self, config, code: str) -> bool:
        """Verify and consume a code for the persisted TOTP secret."""
        if not is_totp_enabled(config):
            return False
        secret = _get_totp_config(config).get("secret", "")
        return await self.consume_totp_code(secret, code)

    async def verify_rotation_secret(
        self, subject: str, current_secret: str, code: str
    ) -> bool:
        """Authorize a subject to rotate its own account-scoped TOTP secret."""

        subject = self._subject_key(subject)
        if not await self.consume_totp_code(current_secret, code):
            return False
        async with self._rotation_lock:
            self._cleanup_expired_rotations()
            self._rotation_verified_subjects.add(subject)
            self._pending_secrets.pop(subject, None)
            self._touch_rotation(subject)
        return True

    async def stage_account_totp_secret(
        self,
        subject: str,
        *,
        current_enabled: bool,
        secret: str,
        code: str,
    ) -> bool:
        """Verify and stage an account TOTP secret without using config state."""

        subject = self._subject_key(subject)
        if current_enabled:
            async with self._rotation_lock:
                self._cleanup_expired_rotations()
                if subject not in self._rotation_verified_subjects:
                    return False
        if not await self.consume_totp_code(secret, code):
            return False
        async with self._rotation_lock:
            self._cleanup_expired_rotations()
            if current_enabled and subject not in self._rotation_verified_subjects:
                return False
            self._rotation_verified_subjects.discard(subject)
            self._pending_secrets[subject] = secret
            self._touch_rotation(subject)
        return True

    async def verify_configured_2fa_code(
        self,
        config,
        code: str,
        *,
        subject: str | None = None,
        include_pending: bool = False,
        allow_recovery: bool = False,
    ) -> TwoFactorCodeType | None:
        """Verify a configured, subject-scoped pending, or recovery code."""
        if not isinstance(code, str) or not code.strip():
            return None
        if await self.consume_configured_totp_code(config, code):
            return TwoFactorCodeType.TOTP
        if include_pending:
            subject = self._subject_key(subject or "")
            async with self._rotation_lock:
                self._cleanup_expired_rotations()
                pending_secret = self._pending_secrets.get(subject)
            if pending_secret and await self.consume_totp_code(pending_secret, code):
                return TwoFactorCodeType.TOTP
        if allow_recovery and verify_recovery_code(config, code):
            return TwoFactorCodeType.RECOVERY
        return None

    async def has_rotation_verification(self, subject: str) -> bool:
        """Return whether this subject has verified the current TOTP secret."""
        subject = self._subject_key(subject)
        async with self._rotation_lock:
            self._cleanup_expired_rotations()
            return subject in self._rotation_verified_subjects

    async def clear_subject(self, subject: str) -> None:
        """Discard pending rotation state for one authenticated subject."""
        subject = self._subject_key(subject)
        async with self._rotation_lock:
            self._pending_secrets.pop(subject, None)
            self._rotation_verified_subjects.discard(subject)
            self._rotation_expires_at.pop(subject, None)

    async def clear_all(self) -> None:
        """Discard pending rotations after the persisted TOTP configuration changes."""
        async with self._rotation_lock:
            self._pending_secrets.clear()
            self._rotation_verified_subjects.clear()
            self._rotation_expires_at.clear()
        async with self._replay_lock:
            self._last_totp_timecodes.clear()


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


def _hash_totp_trusted_device_token(config, token: str) -> str:
    jwt_secret = config["dashboard"].get("jwt_secret", "")
    if not isinstance(jwt_secret, str) or not jwt_secret:
        return ""
    return hmac.new(
        jwt_secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def account_totp_enabled(account) -> bool:
    """Return whether a stable Dashboard account has a complete second factor."""

    return bool(
        getattr(account, "totp_enabled", False)
        and isinstance(getattr(account, "totp_secret", None), str)
        and getattr(account, "totp_secret", "").strip()
        and isinstance(getattr(account, "totp_recovery_code_hash", None), str)
        and getattr(account, "totp_recovery_code_hash", "").strip()
    )


def verify_recovery_code_hash(recovery_code_hash: str, code: str) -> bool:
    """Verify one recovery code against a stored PBKDF2 hash."""

    cleaned = "".join(char for char in code.upper() if char.isalnum())
    if len(cleaned) != RECOVERY_CODE_LENGTH:
        return False
    if not isinstance(recovery_code_hash, str) or not recovery_code_hash:
        return False
    parts = recovery_code_hash.split("$")
    if len(parts) != 4 or parts[0] != _RECOVERY_CODE_KDF_ALGORITHM:
        return False
    try:
        iterations = int(parts[1])
        salt = parts[2]
        expected_digest = parts[3]
    except ValueError, IndexError:
        return False

    try:
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            cleaned.encode("utf-8"),
            bytes.fromhex(salt),
            iterations,
        ).hex()
    except ValueError:
        return False
    return hmac.compare_digest(candidate, expected_digest)


def _hash_account_totp_secret(secret: str) -> str:
    return hashlib.sha256(secret.strip().encode("utf-8")).hexdigest()


async def is_account_totp_trusted_device_valid(
    config,
    db: DatabaseSessionStore,
    *,
    account_id: str,
    totp_secret: str,
    cookie_token: str,
) -> bool:
    """Validate a trusted device bound to one account and its current secret."""

    if not account_id or not totp_secret.strip() or not cookie_token:
        return False
    token_hash = _hash_totp_trusted_device_token(config, cookie_token)
    if not token_hash:
        return False
    await _cleanup_expired_totp_trusted_devices(db)
    async with db.get_db() as session:
        result = await session.execute(
            select(DashboardTrustedDevice).where(
                col(DashboardTrustedDevice.token_hash) == token_hash,
                col(DashboardTrustedDevice.account_id) == account_id,
                col(DashboardTrustedDevice.totp_secret_hash)
                == _hash_account_totp_secret(totp_secret),
                col(DashboardTrustedDevice.expires_at)
                > datetime.datetime.now(datetime.UTC),
            )
        )
        return result.scalar_one_or_none() is not None


async def issue_account_totp_trusted_device(
    config,
    db: DatabaseSessionStore,
    *,
    account_id: str,
    totp_secret: str,
) -> str | None:
    """Issue a trusted-device token bound to one account-scoped second factor."""

    if not account_id or not totp_secret.strip():
        return None
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_totp_trusted_device_token(config, raw_token)
    if not token_hash:
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
            session.add(
                DashboardTrustedDevice(
                    token_hash=token_hash,
                    account_id=account_id,
                    totp_secret_hash=_hash_account_totp_secret(totp_secret),
                    expires_at=expires_at,
                )
            )
    return raw_token


async def revoke_account_totp_trusted_devices(
    db: DatabaseSessionStore, account_id: str
) -> None:
    """Revoke only the trusted devices owned by the supplied account."""

    async with db.get_db() as session:
        async with session.begin():
            await session.execute(
                delete(DashboardTrustedDevice).where(
                    col(DashboardTrustedDevice.account_id) == account_id
                )
            )


async def _cleanup_expired_totp_trusted_devices(db: DatabaseSessionStore) -> None:
    async with db.get_db() as session:
        async with session.begin():
            await session.execute(
                delete(DashboardTrustedDevice).where(
                    col(DashboardTrustedDevice.expires_at)
                    <= datetime.datetime.now(datetime.UTC)
                )
            )


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
    totp_config = _get_totp_config(config)
    return verify_recovery_code_hash(
        str(totp_config.get("recovery_code_hash", "")), code
    )
