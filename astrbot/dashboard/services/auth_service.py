import asyncio
import copy
import datetime
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Any

import jwt
import pyotp

from astrbot import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db.protocols import DatabaseSessionStore
from astrbot.core.utils.auth_password import (
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
    TwoFactorCodeType,
    generate_recovery_code,
    is_totp_enabled,
    is_totp_trusted_device_valid,
    issue_totp_trusted_device,
    revoke_user_trusted_devices,
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
SKIP_DEFAULT_PASSWORD_AUTH_ENV_OLD = "DASHBOARD_SKIP_DEFAULT_PASSWORD_AUTH"
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

    def issue(self, username: str) -> str:
        now = datetime.datetime.now(datetime.UTC)
        payload: dict[str, Any] = {
            "token_type": DASHBOARD_SESSION_TOKEN_TYPE,
            "aud": DASHBOARD_SESSION_AUDIENCE,
            "iss": self.issuer,
            "sub": username,
            "username": username,
            "sid": secrets.token_urlsafe(32),
            "jti": secrets.token_urlsafe(32),
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
        return DashboardSessionPrincipal(username=username, sid=sid, jti=jti)


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
        self.token_validator = token_validator or DashboardTokenValidator(
            self.config["dashboard"].get("jwt_secret", "")
        )

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

    async def totp_setup(
        self,
        post_data: object,
        *,
        subject: str,
    ) -> AuthServiceResult:
        if isinstance(post_data, dict) and post_data.get("secret"):
            secret = post_data["secret"]
            code = post_data.get("code")
            if not isinstance(secret, str) or not secret.strip():
                return self.error("Invalid request payload")

            if not isinstance(code, str) or not code.strip():
                return self.error("TOTP 验证码是必需的")
            if is_totp_enabled(
                self.config
            ) and not await self.totp_runtime_state.has_rotation_verification(subject):
                return self.error("需要先验证当前 TOTP")

            if not await self.totp_runtime_state.stage_pending_totp_secret(
                subject,
                self.config,
                secret,
                code,
            ):
                return self.error("TOTP 验证码无效")
            recovery_code, recovery_code_hash = generate_recovery_code()
            return AuthServiceResult(
                data={
                    "recovery_code": recovery_code,
                    "recovery_code_hash": recovery_code_hash,
                },
                message="TOTP verified",
            )

        if is_totp_enabled(self.config):
            if not isinstance(post_data, dict):
                return self.error("Invalid request payload")

            await self.totp_runtime_state.clear_subject(subject)

            code = post_data.get("code")
            if isinstance(code, str) and code.strip():
                if await self.totp_runtime_state.verify_current_rotation_code(
                    subject,
                    self.config,
                    code,
                ):
                    return AuthServiceResult(data={"secret": pyotp.random_base32()})
                return self.error("当前 TOTP 验证码无效")

            return self.error("需要提供 TOTP 验证码或新密钥")

        return AuthServiceResult(data={"secret": pyotp.random_base32()})

    async def totp_recovery(self) -> AuthServiceResult:
        recovery_code, recovery_code_hash = generate_recovery_code()
        return AuthServiceResult(
            data={
                "recovery_code": recovery_code,
                "recovery_code_hash": recovery_code_hash,
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

        token = self.generate_jwt(username)
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
        username = self.config["dashboard"]["username"]
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

        login_verified = req_username == username and verify_dashboard_password(
            password,
            req_password,
        )

        if not login_verified:
            await asyncio.sleep(3)
            if req_password == "astrbot":
                return self.error(DEFAULT_PASSWORD_LOGIN_FAILURE_MESSAGE)
            if is_md5_dashboard_password(password):
                return self.error(MD5_PASSWORD_LOGIN_FAILURE_MESSAGE)
            return self.error("用户名或密码错误", status_code=401)

        totp_verified = False

        if is_totp_enabled(self.config):
            if not await is_totp_trusted_device_valid(
                self.config,
                self.db,
                trusted_device_cookie_token,
            ):
                if not isinstance(totp_code, str) or not totp_code.strip():
                    return self.error(
                        "需要 TOTP 验证",
                        data={"totp_required": True},
                        status_code=401,
                    )
                verified_type = (
                    await self.totp_runtime_state.verify_configured_2fa_code(
                        self.config,
                        totp_code,
                        allow_recovery=True,
                    )
                )
                if verified_type is TwoFactorCodeType.TOTP:
                    totp_verified = True
                elif verified_type is TwoFactorCodeType.RECOVERY:
                    next_config = copy.deepcopy(dict(self.config))
                    next_config["dashboard"]["totp"] = {
                        "enable": False,
                        "secret": "",
                        "recovery_code_hash": "",
                    }
                    if not await self.config.save_config_async(next_config):
                        return self._config_save_superseded_error()
                    await revoke_user_trusted_devices(self.db)
                    await self.totp_runtime_state.clear_all()
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
            and username == "astrbot"
            and is_default_dashboard_password(password)
            and not self.demo_mode
        ):
            change_pwd_hint = True
            md5_pwd_hint = True
            logger.warning("为了保证安全，请尽快修改默认密码。")
        if password_change_required and not self.demo_mode:
            change_pwd_hint = True
        token = self.generate_jwt(username)
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
            result.trusted_device_token = await issue_totp_trusted_device(
                self.config,
                self.db,
            )
        return result

    async def edit_account(self, post_data: object) -> AuthServiceResult:
        if self.demo_mode:
            return self.error("You are not permitted to do this operation in demo mode")

        # Keep inferred state reads side-effect free so this account change is
        # committed as one snapshot.
        storage_upgraded = await is_password_storage_upgraded(
            self.config,
            persist=False,
        )
        password = get_dashboard_password_hash(self.config, upgraded=storage_upgraded)
        if not isinstance(post_data, dict):
            return self.error("Invalid request payload")

        req_password = post_data.get("password")
        if not isinstance(req_password, str):
            return self.error("Invalid request payload")

        if not verify_dashboard_password(password, req_password):
            return self.error("原密码错误")

        new_pwd = post_data.get("new_password", None)
        new_username = post_data.get("new_username", None)
        password_change_required = await is_password_change_required(
            self.config,
            persist=False,
        )
        if (not storage_upgraded or password_change_required) and not new_pwd:
            return self.error("请设置新密码以完成安全升级")
        if not new_pwd and not new_username:
            return self.error("新用户名和新密码不能同时为空")

        username_to_save = None
        if new_username is not None and new_username != "":
            if not isinstance(new_username, str) or len(new_username.strip()) < 3:
                return self.error("用户名长度至少3位")
            username_to_save = new_username.strip()

        revoke_trusted_devices = False
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
            if is_totp_enabled(self.config):
                revoke_trusted_devices = True

        next_config = copy.deepcopy(dict(self.config))
        next_dashboard_config = next_config["dashboard"]
        if new_pwd:
            set_dashboard_password_hashes(next_dashboard_config, new_pwd)
            set_dashboard_password_security_state(next_dashboard_config)
        if username_to_save:
            next_dashboard_config["username"] = username_to_save

        if not await self.config.save_config_async(next_config):
            return self._config_save_superseded_error()
        if revoke_trusted_devices:
            await revoke_user_trusted_devices(self.db)

        return AuthServiceResult(message="Updated account successfully")

    @staticmethod
    def _config_save_superseded_error() -> AuthServiceResult:
        """Return the standard error when a newer configuration write wins."""
        return AuthService.error(
            "Configuration update was superseded by a newer update. Please retry.",
            status_code=409,
        )

    def generate_jwt(self, username: str) -> str:
        return self.token_validator.issue(username)

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
        value = os.environ.get(name)
        if value is None and name == SKIP_DEFAULT_PASSWORD_AUTH_ENV:
            value = os.environ.get(SKIP_DEFAULT_PASSWORD_AUTH_ENV_OLD)
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

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
