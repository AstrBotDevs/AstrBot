import asyncio
import copy
import datetime
import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
import pyotp
from sqlalchemy import update
from sqlmodel import col, select

from astrbot import logger
from astrbot.core.auth.models import (
    GLOBAL_SCOPE_ID,
    AuthContext,
    Decision,
    Role,
    Subject,
)
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db.po import AuthAuditLog, AuthRoleBinding, DashboardAccount
from astrbot.core.db.protocols import DatabaseSessionStore
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    is_default_dashboard_password,
    is_md5_dashboard_password,
    validate_dashboard_password,
    verify_dashboard_password,
)
from astrbot.core.utils.totp import (
    TOTP_TRUSTED_DEVICE_COOKIE_NAME as _TOTP_TRUSTED_DEVICE_COOKIE_NAME,
)
from astrbot.core.utils.totp import (
    TOTP_TRUSTED_DEVICE_MAX_AGE as _TOTP_TRUSTED_DEVICE_MAX_AGE,
)
from astrbot.core.utils.totp import (
    TotpRuntimeState,
    account_totp_enabled,
    generate_recovery_code,
    is_account_totp_trusted_device_valid,
    issue_account_totp_trusted_device,
    revoke_account_totp_trusted_devices,
    verify_recovery_code_hash,
)
from astrbot.dashboard.password_state import (
    get_dashboard_password_hash,
    is_password_change_required,
    is_password_storage_upgraded,
    set_dashboard_password_hashes,
    set_dashboard_password_security_state,
)

DASHBOARD_JWT_COOKIE_NAME = "astrbot_dashboard_jwt"
DASHBOARD_JWT_COOKIE_MAX_AGE = 7 * 24 * 60 * 60
DASHBOARD_SESSION_TOKEN_TYPE = "dashboard_session"
DASHBOARD_SESSION_AUDIENCE = "astrbot-dashboard"
DASHBOARD_SESSION_ISSUER_PURPOSE = b"dashboard-session-issuer-v1"
SKIP_DEFAULT_PASSWORD_AUTH_ENV = "ASTRBOT_DASHBOARD_SKIP_DEFAULT_PASSWORD_AUTH"
LOCAL_DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}
DEFAULT_PASSWORD_LOGIN_FAILURE_MESSAGE = (
    "Login failed. If this is your first time using AstrBot, the old default "
    "astrbot password has been replaced by a random strong password printed in "
    "the startup logs. Check the initial password in the logs and try again. "
    "Learn more: https://docs.astrbot.app/en/faq.html\n\n"
    "登录失败。如果您是初次使用，旧版默认 astrbot 密码已改为启动日志中输出的"
    "随机强密码。请使用日志中提供的的初始密码来登录。了解更多："
    "https://docs.astrbot.app/faq.html"
)
MD5_PASSWORD_LOGIN_FAILURE_MESSAGE = (
    "Incorrect username or password. If you cannot log in after upgrading "
    "AstrBot even though the password is correct, see "
    "https://docs.astrbot.app/en/faq.html\n\n"
    "用户名或密码错误。如果你在升级 AstrBot 后遇到了密码正确但无法登录的情况，"
    "请参考 https://docs.astrbot.app/faq.html"
)
TOTP_TRUSTED_DEVICE_COOKIE_NAME = _TOTP_TRUSTED_DEVICE_COOKIE_NAME
TOTP_TRUSTED_DEVICE_MAX_AGE = _TOTP_TRUSTED_DEVICE_MAX_AGE


@dataclass
class AuthServiceResult:
    status: str = "ok"
    data: dict | None = None
    message: str | None = None
    status_code: int = 200
    jwt_token: str | None = None
    trusted_device_token: str | None = None


@dataclass(frozen=True)
class DashboardSessionPrincipal:
    username: str
    sid: str
    jti: str
    account_id: str | None = None
    auth_strength: str = "password"
    issued_at: datetime.datetime | None = None

    @property
    def subject(self) -> Subject:
        return Subject.dashboard_session(self.sid, self.username)

    @property
    def account_subject(self) -> Subject | None:
        return (
            Subject.dashboard_account(self.account_id, self.username)
            if self.account_id
            else None
        )


def derive_dashboard_secret(jwt_secret: str, purpose: bytes) -> bytes:
    """Derive a purpose-bound secret from the persisted Dashboard secret."""
    if not jwt_secret:
        raise ValueError("JWT secret is not set in the cmd_config.")
    return hmac.new(jwt_secret.encode(), purpose, hashlib.sha256).digest()


class DashboardTokenValidator:
    """Issue and validate Dashboard session JWTs with mutually exclusive rules."""

    _REQUIRED_CLAIMS = (
        "exp",
        "iat",
        "iss",
        "aud",
        "sub",
        "username",
        "sid",
        "jti",
        "token_type",
    )

    def __init__(self, jwt_secret: str) -> None:
        if not jwt_secret:
            raise ValueError("JWT secret is not set in the cmd_config.")
        self._jwt_secret = jwt_secret
        issuer_digest = derive_dashboard_secret(
            jwt_secret,
            DASHBOARD_SESSION_ISSUER_PURPOSE,
        ).hex()
        self.issuer = f"urn:astrbot:dashboard:{issuer_digest}"

    def issue(
        self,
        username: str,
        *,
        account_id: str | None = None,
        auth_strength: str = "password",
    ) -> str:
        now = datetime.datetime.now(datetime.UTC)
        payload: dict[str, Any] = {
            "token_type": DASHBOARD_SESSION_TOKEN_TYPE,
            "aud": DASHBOARD_SESSION_AUDIENCE,
            "iss": self.issuer,
            "sub": username,
            "username": username,
            # Dashboard session IDs become authorization subject components;
            # use hex tokens so they satisfy the canonical identifier grammar
            # (URL-safe base64 may contain ``_``).
            "sid": secrets.token_hex(32),
            "jti": secrets.token_hex(32),
            "account_id": account_id,
            "auth_strength": auth_strength,
            "iat": now,
            "exp": now + datetime.timedelta(seconds=DASHBOARD_JWT_COOKIE_MAX_AGE),
        }
        return jwt.encode(payload, self._jwt_secret, algorithm="HS256")

    def validate(self, token: str) -> DashboardSessionPrincipal:
        payload = jwt.decode(
            token,
            self._jwt_secret,
            algorithms=["HS256"],
            audience=DASHBOARD_SESSION_AUDIENCE,
            issuer=self.issuer,
            options={"require": list(self._REQUIRED_CLAIMS)},
        )
        if payload.get("token_type") != DASHBOARD_SESSION_TOKEN_TYPE:
            raise jwt.InvalidTokenError("Invalid Dashboard token type")

        username = payload.get("username")
        subject = payload.get("sub")
        sid = payload.get("sid")
        jti = payload.get("jti")
        if (
            not isinstance(username, str)
            or not username.strip()
            or subject != username
            or not isinstance(sid, str)
            or not sid
            or not isinstance(jti, str)
            or not jti
        ):
            raise jwt.InvalidTokenError("Invalid Dashboard token claims")
        account_id = payload.get("account_id")
        auth_strength = payload.get("auth_strength", "password")
        if account_id is not None and (
            not isinstance(account_id, str) or not account_id
        ):
            raise jwt.InvalidTokenError("Invalid Dashboard account claim")
        if auth_strength not in {"password", "totp", "step_up"}:
            raise jwt.InvalidTokenError("Invalid Dashboard auth strength")
        issued = (
            datetime.datetime.fromtimestamp(float(payload["iat"]), datetime.UTC)
            if isinstance(payload.get("iat"), int | float)
            else None
        )
        return DashboardSessionPrincipal(
            username=username,
            sid=sid,
            jti=jti,
            account_id=account_id,
            auth_strength=auth_strength,
            issued_at=issued,
        )


class AuthService:
    def __init__(
        self,
        db: DatabaseSessionStore,
        config: AstrBotConfig,
        *,
        demo_mode: bool,
        totp_runtime_state: TotpRuntimeState,
        token_validator: DashboardTokenValidator | None = None,
    ) -> None:
        self.db = db
        self.config = config
        self.demo_mode = demo_mode
        self.totp_runtime_state = totp_runtime_state
        self._account_mutation_lock = asyncio.Lock()
        self.token_validator = token_validator or DashboardTokenValidator(
            self.config["dashboard"].get("jwt_secret", "")
        )

    @staticmethod
    def _account_audit_record(
        *,
        actor: Subject,
        context: AuthContext,
        decision: Decision,
        reason: str,
        metadata: dict[str, Any],
    ) -> AuthAuditLog:
        """Create the business audit row committed with account mutations."""

        return AuthAuditLog(
            audit_id=str(uuid.uuid4()),
            request_id=context.request_id,
            subject_id=actor.id,
            effective_role=(
                decision.effective_role.value if decision.effective_role else None
            ),
            source=context.source,
            config_id=context.config_id,
            action=decision.action,
            resource_id=decision.resource.id,
            decision="allow",
            reason=reason,
            step_up_id=decision.step_up_id,
            outcome="allow",
            metadata_json=metadata,
        )

    async def _ensure_dashboard_account(
        self, username: str, password_hash: str, *, sync_password: bool = False
    ) -> DashboardAccount:
        """Create the first stable Dashboard account and root binding."""

        async with self.db.get_db() as session:
            async with session.begin():
                account = (
                    await session.execute(
                        select(DashboardAccount).where(
                            col(DashboardAccount.username) == username
                        )
                    )
                ).scalar_one_or_none()
                if account is None:
                    account = DashboardAccount(
                        username=username,
                        password_hash=password_hash,
                    )
                    session.add(account)
                    await session.flush()
                    root = (
                        await session.execute(
                            select(AuthRoleBinding).where(
                                col(AuthRoleBinding.role) == Role.ROOT.value,
                                col(AuthRoleBinding.scope_type) == "global",
                                col(AuthRoleBinding.scope_id) == "global",
                                col(AuthRoleBinding.config_id) == GLOBAL_SCOPE_ID,
                                col(AuthRoleBinding.revoked_at).is_(None),
                                (col(AuthRoleBinding.expires_at).is_(None))
                                | (
                                    col(AuthRoleBinding.expires_at)
                                    > datetime.datetime.now(datetime.UTC)
                                ),
                            )
                        )
                    ).scalar_one_or_none()
                    if root is None:
                        session.add(
                            AuthRoleBinding(
                                subject_id=f"dashboard-account:{account.account_id}",
                                role=Role.ROOT.value,
                                scope_type="global",
                                scope_id="global",
                                config_id=GLOBAL_SCOPE_ID,
                                source="bootstrap",
                                created_by="system:bootstrap",
                                metadata_json={"bootstrap": True},
                            )
                        )
                else:
                    # A per-account password is authoritative after setup.
                    # Syncing is only used by the explicit first-account setup.
                    if sync_password:
                        account.password_hash = password_hash
                    account.last_login_at = datetime.datetime.now(datetime.UTC)
                await session.flush()
                return account

    async def _find_dashboard_account(self, username: str) -> DashboardAccount | None:
        """Return the active stable account for a Dashboard username."""

        async with self.db.get_db() as session:
            return (
                await session.execute(
                    select(DashboardAccount).where(
                        col(DashboardAccount.username) == username,
                        col(DashboardAccount.is_active).is_(True),
                    )
                )
            ).scalar_one_or_none()

    async def validate_dashboard_principal(
        self, principal: DashboardSessionPrincipal
    ) -> bool:
        """Reject stale, renamed, or disabled Dashboard tokens."""

        if not principal.account_id:
            return False
        async with self.db.get_db() as session:
            account = (
                await session.execute(
                    select(DashboardAccount).where(
                        col(DashboardAccount.account_id) == principal.account_id,
                        col(DashboardAccount.username) == principal.username,
                        col(DashboardAccount.is_active).is_(True),
                    )
                )
            ).scalar_one_or_none()
            return account is not None

    async def list_dashboard_accounts(self) -> list[DashboardAccount]:
        """List stable control-plane accounts without exposing password hashes."""

        async with self.db.get_db() as session:
            return list(
                (
                    await session.execute(
                        select(DashboardAccount).order_by(
                            col(DashboardAccount.created_at).asc()
                        )
                    )
                ).scalars()
            )

    async def has_dashboard_accounts(self) -> bool:
        """Return whether a stable Dashboard account has been created."""

        async with self.db.get_db() as session:
            return (
                await session.execute(select(DashboardAccount.account_id).limit(1))
            ).scalar_one_or_none() is not None

    async def create_dashboard_account(
        self,
        *,
        username: str,
        password: str,
        created_by: str,
    ) -> DashboardAccount:
        """Create an independently authenticated Dashboard account."""

        normalized_username = username.strip()
        if len(normalized_username) < 3:
            raise ValueError("Username must be at least 3 characters")
        validate_dashboard_password(password)
        async with self.db.get_db() as session:
            async with session.begin():
                existing = (
                    await session.execute(
                        select(DashboardAccount).where(
                            col(DashboardAccount.username) == normalized_username
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    raise ValueError("Dashboard username already exists")
                account = DashboardAccount(
                    username=normalized_username,
                    password_hash=hash_dashboard_password(password),
                    created_by=created_by,
                )
                session.add(account)
                await session.flush()
                return account

    async def create_dashboard_account_with_role(
        self,
        *,
        username: str,
        password: str,
        created_by: str,
        role: Role,
        actor: Subject | None = None,
        audit_context: AuthContext | None = None,
        audit_decision: Decision | None = None,
    ) -> tuple[DashboardAccount, AuthRoleBinding]:
        """Atomically create a Dashboard identity and its global role binding."""

        if role not in {Role.ROOT, Role.OPERATOR}:
            raise ValueError("Dashboard accounts require a global control-plane role")
        normalized_username = username.strip()
        if len(normalized_username) < 3:
            raise ValueError("Username must be at least 3 characters")
        validate_dashboard_password(password)
        async with self._account_mutation_lock:
            async with self.db.get_db() as session:
                async with session.begin():
                    existing = (
                        await session.execute(
                            select(DashboardAccount).where(
                                col(DashboardAccount.username) == normalized_username
                            )
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        raise ValueError("Dashboard username already exists")
                    account = DashboardAccount(
                        username=normalized_username,
                        password_hash=hash_dashboard_password(password),
                        created_by=created_by,
                    )
                    session.add(account)
                    await session.flush()
                    binding = AuthRoleBinding(
                        subject_id=Subject.dashboard_account(
                            account.account_id, account.username
                        ).id,
                        role=role.value,
                        scope_type="global",
                        scope_id="global",
                        config_id=GLOBAL_SCOPE_ID,
                        source="explicit",
                        created_by=created_by,
                        metadata_json={"account_creation": True},
                    )
                    session.add(binding)
                    await session.flush()
                    if (
                        actor is not None
                        and audit_context is not None
                        and audit_decision
                    ):
                        session.add(
                            self._account_audit_record(
                                actor=actor,
                                context=audit_context,
                                decision=audit_decision,
                                reason="account_created",
                                metadata={
                                    "account_id": account.account_id,
                                    "binding_id": binding.binding_id,
                                    "role": role.value,
                                },
                            )
                        )
                    return account, binding

    async def update_dashboard_account(
        self,
        *,
        account_id: str,
        username: str | None = None,
        password: str | None = None,
        is_active: bool | None = None,
        actor: Subject | None = None,
        audit_context: AuthContext | None = None,
        audit_decision: Decision | None = None,
    ) -> DashboardAccount | None:
        """Update one stable account and revoke its bindings when disabled."""

        if username is not None and len(username.strip()) < 3:
            raise ValueError("Username must be at least 3 characters")
        if password is not None:
            validate_dashboard_password(password)
        async with self._account_mutation_lock:
            async with self.db.get_db() as session:
                async with session.begin():
                    account = (
                        await session.execute(
                            select(DashboardAccount).where(
                                col(DashboardAccount.account_id) == account_id
                            )
                        )
                    ).scalar_one_or_none()
                    if account is None:
                        return None
                    if is_active is False and account.is_active:
                        now = datetime.datetime.now(datetime.UTC)
                        root_subjects = set(
                            (
                                await session.execute(
                                    select(AuthRoleBinding.subject_id).where(
                                        col(AuthRoleBinding.role) == Role.ROOT.value,
                                        col(AuthRoleBinding.scope_type) == "global",
                                        col(AuthRoleBinding.scope_id) == "global",
                                        col(AuthRoleBinding.config_id)
                                        == GLOBAL_SCOPE_ID,
                                        col(AuthRoleBinding.revoked_at).is_(None),
                                        (col(AuthRoleBinding.expires_at).is_(None))
                                        | (col(AuthRoleBinding.expires_at) > now),
                                    )
                                )
                            ).scalars()
                        )
                        active_roots = (
                            await session.execute(
                                select(DashboardAccount.account_id).where(
                                    col(DashboardAccount.is_active).is_(True)
                                )
                            )
                        ).scalars()
                        if (
                            f"dashboard-account:{account_id}" in root_subjects
                            and sum(
                                f"dashboard-account:{root_id}" in root_subjects
                                for root_id in active_roots
                            )
                            <= 1
                        ):
                            raise ValueError("Cannot deactivate the last root account")
                    if username is not None:
                        normalized_username = username.strip()
                        duplicate = (
                            await session.execute(
                                select(DashboardAccount).where(
                                    col(DashboardAccount.username)
                                    == normalized_username,
                                    col(DashboardAccount.account_id) != account_id,
                                )
                            )
                        ).scalar_one_or_none()
                        if duplicate is not None:
                            raise ValueError("Dashboard username already exists")
                        account.username = normalized_username
                    if password is not None:
                        account.password_hash = hash_dashboard_password(password)
                    if is_active is not None:
                        account.is_active = is_active
                        if not is_active:
                            now = datetime.datetime.now(datetime.UTC)
                            await session.execute(
                                update(AuthRoleBinding)
                                .where(
                                    col(AuthRoleBinding.subject_id)
                                    == Subject.dashboard_account(
                                        account.account_id, account.username
                                    ).id,
                                    col(AuthRoleBinding.revoked_at).is_(None),
                                )
                                .values(
                                    revoked_at=now, revoked_by="system:account-disable"
                                )
                            )
                    if (
                        actor is not None
                        and audit_context is not None
                        and audit_decision
                    ):
                        session.add(
                            self._account_audit_record(
                                actor=actor,
                                context=audit_context,
                                decision=audit_decision,
                                reason="account_updated",
                                metadata={
                                    "account_id": account.account_id,
                                    "is_active": account.is_active,
                                    "password_changed": password is not None,
                                    "username_changed": username is not None,
                                },
                            )
                        )
                    return account

    async def setup_status(self) -> AuthServiceResult:
        return AuthServiceResult(
            data={
                "setup_required": await self.is_setup_required(),
                "skip_default_password_auth": self.can_skip_default_password_auth(),
                "password_upgrade_required": not await is_password_storage_upgraded(
                    self.config,
                ),
            }
        )

    async def verify_step_up_factor(
        self,
        *,
        account_id: str,
        password: str | None = None,
        code: str | None = None,
    ) -> str | None:
        """Reauthenticate one Dashboard factor without issuing a session token."""

        async with self.db.get_db() as session:
            account = (
                await session.execute(
                    select(DashboardAccount).where(
                        col(DashboardAccount.account_id) == account_id,
                        col(DashboardAccount.is_active).is_(True),
                    )
                )
            ).scalar_one_or_none()
        if account is None:
            return None
        if isinstance(password, str) and password:
            if verify_dashboard_password(account.password_hash, password):
                return "password"
        if isinstance(code, str) and code.strip() and account_totp_enabled(account):
            if await self.totp_runtime_state.consume_totp_code(
                account.totp_secret, code.strip()
            ):
                return "totp"
        return None

    async def totp_setup(
        self,
        post_data: object,
        *,
        subject: str,
        account_id: str,
    ) -> AuthServiceResult:
        async with self.db.get_db() as session:
            account = (
                await session.execute(
                    select(DashboardAccount).where(
                        col(DashboardAccount.account_id) == account_id,
                        col(DashboardAccount.is_active).is_(True),
                    )
                )
            ).scalar_one_or_none()
        if account is None:
            return self.error("Dashboard account is unavailable", status_code=401)
        if isinstance(post_data, dict) and post_data.get("secret"):
            secret = post_data["secret"]
            code = post_data.get("code")
            if not isinstance(secret, str) or not secret.strip():
                return self.error("Invalid request payload")

            if not isinstance(code, str) or not code.strip():
                return self.error("TOTP 验证码是必需的")
            if account_totp_enabled(
                account
            ) and not await self.totp_runtime_state.has_rotation_verification(subject):
                return self.error("需要先验证当前 TOTP")

            if not await self.totp_runtime_state.stage_account_totp_secret(
                subject,
                current_enabled=account_totp_enabled(account),
                secret=secret,
                code=code,
            ):
                return self.error("TOTP 验证码无效")
            recovery_code, recovery_code_hash = generate_recovery_code()
            async with self.db.get_db() as session:
                async with session.begin():
                    persisted = (
                        await session.execute(
                            select(DashboardAccount).where(
                                col(DashboardAccount.account_id) == account_id,
                                col(DashboardAccount.is_active).is_(True),
                            )
                        )
                    ).scalar_one_or_none()
                    if persisted is None:
                        return self.error(
                            "Dashboard account is unavailable", status_code=401
                        )
                    persisted.totp_enabled = True
                    persisted.totp_secret = secret.strip()
                    persisted.totp_recovery_code_hash = recovery_code_hash
            await revoke_account_totp_trusted_devices(self.db, account_id)
            return AuthServiceResult(
                data={
                    "recovery_code": recovery_code,
                    "recovery_code_hash": recovery_code_hash,
                    "enabled": True,
                },
                message="TOTP verified",
            )

        if account_totp_enabled(account):
            if not isinstance(post_data, dict):
                return self.error("Invalid request payload")

            await self.totp_runtime_state.clear_subject(subject)

            code = post_data.get("code")
            if isinstance(code, str) and code.strip():
                if await self.totp_runtime_state.consume_totp_code(
                    account.totp_secret, code
                ):
                    async with self.totp_runtime_state._rotation_lock:
                        self.totp_runtime_state._rotation_verified_subjects.add(
                            self.totp_runtime_state._subject_key(subject)
                        )
                    return AuthServiceResult(data={"secret": pyotp.random_base32()})
                if await self.totp_runtime_state.verify_rotation_secret(
                    subject, account.totp_secret, code
                ):
                    return AuthServiceResult(data={"secret": pyotp.random_base32()})
                # Direct setup callers may supply the current factor in the
                # same request; accept it as the session-scoped verification
                # instead of requiring a separate browser round trip.
                if await self.totp_runtime_state.consume_totp_code(
                    account.totp_secret, code
                ):
                    return AuthServiceResult(data={"secret": pyotp.random_base32()})
                return self.error("当前 TOTP 验证码无效")

            return self.error("需要提供 TOTP 验证码或新密钥")

        return AuthServiceResult(data={"secret": pyotp.random_base32()})

    async def totp_recovery(self, *, account_id: str) -> AuthServiceResult:
        recovery_code, recovery_code_hash = generate_recovery_code()
        async with self.db.get_db() as session:
            async with session.begin():
                account = (
                    await session.execute(
                        select(DashboardAccount).where(
                            col(DashboardAccount.account_id) == account_id,
                            col(DashboardAccount.is_active).is_(True),
                        )
                    )
                ).scalar_one_or_none()
                if account is None or not account_totp_enabled(account):
                    return self.error("TOTP is not enabled", status_code=400)
                account.totp_recovery_code_hash = recovery_code_hash
        await revoke_account_totp_trusted_devices(self.db, account_id)
        return AuthServiceResult(
            data={
                "recovery_code": recovery_code,
            }
        )

    async def discard_totp_rotation(self, subject: str) -> None:
        """Discard a pending TOTP rotation when its dashboard session ends."""
        await self.totp_runtime_state.clear_subject(subject)

    async def setup(self, post_data: object) -> AuthServiceResult:
        if not self.can_skip_default_password_auth():
            return self.error("Setup without password is not enabled")
        if not await self.is_setup_required():
            return self.error("Setup is not required")

        return await self.complete_setup(post_data)

    async def setup_authenticated(
        self,
        post_data: object,
        authenticated_username,
    ) -> AuthServiceResult:
        if not await self.is_setup_required():
            return self.error("Setup is not required")
        if not isinstance(authenticated_username, str):
            return self.error("未授权")

        return await self.complete_setup(post_data)

    async def complete_setup(self, post_data: object) -> AuthServiceResult:
        if not isinstance(post_data, dict):
            return self.error("Invalid request payload")

        new_username = post_data.get("username")
        new_password = post_data.get("password")
        confirm_password = post_data.get("confirm_password")
        if not isinstance(new_username, str) or len(new_username.strip()) < 3:
            return self.error("用户名长度至少3位")
        if not isinstance(new_password, str):
            return self.error("新密码无效")
        if not isinstance(confirm_password, str) or confirm_password != new_password:
            return self.error("两次输入的新密码不一致")

        try:
            validate_dashboard_password(new_password)
        except ValueError as exc:
            return self.error(str(exc))

        username = new_username.strip()
        next_config = copy.deepcopy(dict(self.config))
        next_dashboard_config = next_config["dashboard"]
        next_dashboard_config["username"] = username
        set_dashboard_password_hashes(next_dashboard_config, new_password)
        set_dashboard_password_security_state(next_dashboard_config)
        if not await self.config.save_config_async(next_config):
            return self._config_save_superseded_error()

        account = await self._ensure_dashboard_account(
            username,
            str(next_dashboard_config.get("pbkdf2_password", "")),
            sync_password=True,
        )
        token = self.generate_jwt(username, account_id=account.account_id)
        return AuthServiceResult(
            data={
                "token": token,
                "username": username,
                "change_pwd_hint": False,
                "md5_pwd_hint": False,
                "password_upgrade_required": False,
            },
            message="Setup completed successfully",
            jwt_token=token,
        )

    async def login(
        self,
        post_data: object,
        *,
        trusted_device_cookie_token: str,
    ) -> AuthServiceResult:
        configured_username = self.config["dashboard"]["username"]
        storage_upgraded = await is_password_storage_upgraded(self.config)
        password = get_dashboard_password_hash(self.config, upgraded=storage_upgraded)

        req_username = (
            post_data.get("username") if isinstance(post_data, dict) else None
        )
        req_password = (
            post_data.get("password") if isinstance(post_data, dict) else None
        )
        totp_code = post_data.get("code") if isinstance(post_data, dict) else None
        trust_device_flag = (
            post_data.get("trust_device_flag") is True
            if isinstance(post_data, dict)
            else False
        )
        if not isinstance(req_username, str) or not isinstance(req_password, str):
            return self.error("Invalid request payload")

        account = await self._find_dashboard_account(req_username)
        bootstrap_account = (
            account is None
            and req_username == configured_username
            and not await self.has_dashboard_accounts()
        )
        if bootstrap_account:
            # A fresh deployment verifies the configured bootstrap credential
            # once, then persists the account as the authorization principal.
            login_verified = verify_dashboard_password(password, req_password)
        else:
            login_verified = account is not None and verify_dashboard_password(
                account.password_hash, req_password
            )

        if not login_verified:
            await asyncio.sleep(3)
            if req_password == "astrbot":
                return self.error(DEFAULT_PASSWORD_LOGIN_FAILURE_MESSAGE)
            if is_md5_dashboard_password(password):
                return self.error(MD5_PASSWORD_LOGIN_FAILURE_MESSAGE)
            return self.error("用户名或密码错误", status_code=401)

        if account is None:
            account = await self._ensure_dashboard_account(
                configured_username, password
            )

        totp_verified = False
        if account_totp_enabled(account):
            trusted = await is_account_totp_trusted_device_valid(
                self.config,
                self.db,
                account_id=account.account_id,
                totp_secret=account.totp_secret,
                cookie_token=trusted_device_cookie_token,
            )
            if not trusted:
                if not isinstance(totp_code, str) or not totp_code.strip():
                    return self.error(
                        "需要 TOTP 验证",
                        data={"totp_required": True},
                        status_code=401,
                    )
                if await self.totp_runtime_state.consume_totp_code(
                    account.totp_secret, totp_code
                ):
                    totp_verified = True
                elif verify_recovery_code_hash(
                    account.totp_recovery_code_hash, totp_code
                ):
                    async with self.db.get_db() as session:
                        async with session.begin():
                            persisted = (
                                await session.execute(
                                    select(DashboardAccount).where(
                                        col(DashboardAccount.account_id)
                                        == account.account_id
                                    )
                                )
                            ).scalar_one_or_none()
                            if persisted is None:
                                return self.error(
                                    "Dashboard account is unavailable", status_code=401
                                )
                            persisted.totp_enabled = False
                            persisted.totp_secret = ""
                            persisted.totp_recovery_code_hash = ""
                    # Keep the persisted configuration snapshot aligned with
                    # the account-level factor for config export consumers.
                    dashboard_totp = self.config.get("dashboard", {}).get("totp")
                    if isinstance(dashboard_totp, dict):
                        next_config = copy.deepcopy(dict(self.config))
                        next_config["dashboard"]["totp"] = {
                            "enable": False,
                            "secret": "",
                            "recovery_code_hash": "",
                        }
                        await self.config.save_config_async(next_config)
                    await revoke_account_totp_trusted_devices(
                        self.db, account.account_id
                    )
                    await self.totp_runtime_state.clear_subject(
                        f"dashboard-account:{account.account_id}"
                    )
                elif len(totp_code) == 6 and totp_code.isdigit():
                    return self.error("TOTP 验证码无效", status_code=401)
                else:
                    return self.error("恢复码无效", status_code=401)

        change_pwd_hint = False
        md5_pwd_hint = is_md5_dashboard_password(password)
        password_change_required = await is_password_change_required(
            self.config,
        )
        if (
            storage_upgraded
            and configured_username == "astrbot"
            and is_default_dashboard_password(password)
            and not self.demo_mode
        ):
            change_pwd_hint = True
            md5_pwd_hint = True
            logger.warning("为了保证安全，请尽快修改默认密码。")
        if password_change_required and not self.demo_mode:
            change_pwd_hint = True
        async with self.db.get_db() as session:
            async with session.begin():
                persisted = (
                    await session.execute(
                        select(DashboardAccount).where(
                            col(DashboardAccount.account_id) == account.account_id
                        )
                    )
                ).scalar_one_or_none()
                if persisted is None or not persisted.is_active:
                    return self.error(
                        "Dashboard account is unavailable", status_code=401
                    )
                persisted.last_login_at = datetime.datetime.now(datetime.UTC)
                account = persisted
        username = account.username
        token = self.generate_jwt(
            username,
            account_id=account.account_id,
            auth_strength="totp" if totp_verified else "password",
        )
        result = AuthServiceResult(
            data={
                "token": token,
                "username": username,
                "change_pwd_hint": change_pwd_hint,
                "md5_pwd_hint": md5_pwd_hint,
                "password_upgrade_required": not storage_upgraded,
            },
            jwt_token=token,
        )

        if totp_verified and trust_device_flag:
            result.trusted_device_token = await issue_account_totp_trusted_device(
                self.config,
                self.db,
                account_id=account.account_id,
                totp_secret=account.totp_secret,
            )
        return result

    async def edit_account(
        self, post_data: object, *, account_id: str | None = None
    ) -> AuthServiceResult:
        if self.demo_mode:
            return self.error("You are not permitted to do this operation in demo mode")

        if not isinstance(post_data, dict):
            return self.error("Invalid request payload")

        if not account_id:
            return self.error("Dashboard account id is required")

        req_password = post_data.get("password")
        if not isinstance(req_password, str):
            return self.error("Invalid request payload")

        async with self.db.get_db() as session:
            account = (
                await session.execute(
                    select(DashboardAccount).where(
                        col(DashboardAccount.account_id) == account_id,
                        col(DashboardAccount.is_active).is_(True),
                    )
                )
            ).scalar_one_or_none()
        password_ok = account is not None and verify_dashboard_password(
            account.password_hash, req_password
        )
        if account is None or not password_ok:
            return self.error("原密码错误")

        new_pwd = post_data.get("new_password", None)
        new_username = post_data.get("new_username", None)
        if not new_pwd and not new_username:
            return self.error("新用户名和新密码不能同时为空")

        username_to_save = None
        if new_username is not None and new_username != "":
            if not isinstance(new_username, str) or len(new_username.strip()) < 3:
                return self.error("用户名长度至少3位")
            username_to_save = new_username.strip()

        # A username-only edit is blocked while the initial password change is
        # still required, keeping the signed session subject in sync.
        if not new_pwd and (
            not await is_password_storage_upgraded(self.config, persist=False)
            or await is_password_change_required(self.config)
        ):
            return self.error("请先修改密码")

        if new_pwd:
            if not isinstance(new_pwd, str):
                return self.error("新密码无效")
            confirm_pwd = post_data.get("confirm_password", None)
            if not isinstance(confirm_pwd, str) or confirm_pwd != new_pwd:
                return self.error("两次输入的新密码不一致")
            try:
                validate_dashboard_password(new_pwd)
            except ValueError as exc:
                return self.error(str(exc))
        await self.update_dashboard_account(
            account_id=account_id,
            username=username_to_save,
            password=new_pwd if new_pwd else None,
        )
        if username_to_save:
            next_config = copy.deepcopy(dict(self.config))
            next_config["dashboard"]["username"] = username_to_save
            await self.config.save_config_async(next_config)
        if new_pwd:
            next_config = copy.deepcopy(dict(self.config))
            set_dashboard_password_hashes(next_config["dashboard"], new_pwd)
            set_dashboard_password_security_state(next_config["dashboard"])
            await self.config.save_config_async(next_config)
        if new_pwd:
            await revoke_account_totp_trusted_devices(self.db, account_id)

        return AuthServiceResult(message="Updated account successfully")

    @staticmethod
    def _config_save_superseded_error() -> AuthServiceResult:
        """Return the standard error when a newer configuration write wins."""
        return AuthService.error(
            "Configuration update was superseded by a newer update. Please retry.",
            status_code=409,
        )

    def generate_jwt(
        self,
        username: str,
        *,
        account_id: str | None = None,
        auth_strength: str = "password",
    ) -> str:
        return self.token_validator.issue(
            username, account_id=account_id, auth_strength=auth_strength
        )

    async def is_setup_required(self) -> bool:
        if self.demo_mode:
            return False

        dashboard_config = self.config["dashboard"]
        password_change_required = await is_password_change_required(
            self.config,
        )
        if password_change_required:
            return True

        storage_upgraded = await is_password_storage_upgraded(self.config)
        if not storage_upgraded:
            return False

        return dashboard_config.get(
            "username"
        ) == "astrbot" and is_default_dashboard_password(
            dashboard_config.get("pbkdf2_password", "")
        )

    def can_skip_default_password_auth(self) -> bool:
        if not self.env_flag_enabled(SKIP_DEFAULT_PASSWORD_AUTH_ENV):
            return False
        host = (
            os.environ.get("DASHBOARD_HOST")
            or os.environ.get("ASTRBOT_DASHBOARD_HOST")
            or self.config["dashboard"].get("host", "")
        )
        return str(host).strip().lower() in LOCAL_DASHBOARD_HOSTS

    @staticmethod
    def env_flag_enabled(name: str) -> bool:
        value = os.environ.get(name, "")
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def error(
        message: str,
        *,
        data: dict | None = None,
        status_code: int = 200,
    ) -> AuthServiceResult:
        return AuthServiceResult(
            status="error",
            data=data,
            message=message,
            status_code=status_code,
        )
