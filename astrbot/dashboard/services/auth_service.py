from __future__ import annotations

import asyncio
import datetime
import os
from dataclasses import dataclass

import jwt
import pyotp

from astrbot import logger
from astrbot.core import DEMO_MODE
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db import BaseDatabase
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
    TwoFactorCodeType,
    consume_configured_totp_code,
    consume_rotation_verified,
    consume_totp_code,
    generate_recovery_code,
    is_totp_enabled,
    is_totp_trusted_device_valid,
    issue_totp_trusted_device,
    revoke_user_trusted_devices,
    set_pending_totp_secret,
    set_rotation_verified,
    verify_configured_2fa_code,
)
from astrbot.dashboard.password_state import (
    get_dashboard_password_hash,
    is_password_change_required,
    is_password_storage_upgraded,
    set_dashboard_password_hashes,
    set_password_change_required,
    set_password_storage_upgraded,
)

ALL_OPEN_API_SCOPES = (
    "bot",
    "provider",
    "persona",
    "im",
    "config",
    "chat",
    "data",
    "file",
    "plugin",
    "mcp",
    "skill",
)

OPEN_API_SCOPE_INCLUDES = {
    "config": ("bot", "provider"),
}

DASHBOARD_JWT_COOKIE_NAME = "astrbot_dashboard_jwt"
DASHBOARD_JWT_COOKIE_MAX_AGE = 7 * 24 * 60 * 60
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


class AuthService:
    def __init__(
        self,
        db: BaseDatabase,
        config: AstrBotConfig,
        *,
        demo_mode: bool = DEMO_MODE,
    ) -> None:
        self.db = db
        self.config = config
        self.demo_mode = demo_mode

    async def setup_status(self) -> AuthServiceResult:
        return AuthServiceResult(
            data={
                "setup_required": await self.is_setup_required(),
                "skip_default_password_auth": self.can_skip_default_password_auth(),
                "password_upgrade_required": not await is_password_storage_upgraded(
                    self.db,
                    self.config,
                ),
            }
        )

    async def totp_setup(self, post_data: object) -> AuthServiceResult:
        if isinstance(post_data, dict) and post_data.get("secret"):
            secret = post_data["secret"]
            code = post_data.get("code")
            if not isinstance(secret, str) or not secret.strip():
                return self.error("Invalid request payload")

            if not isinstance(code, str) or not code.strip():
                return self.error("TOTP 验证码是必需的")
            if not await consume_totp_code(secret, code):
                return self.error("TOTP 验证码无效")

            if is_totp_enabled(self.config) and not consume_rotation_verified():
                return self.error("需要先验证当前 TOTP")

            set_pending_totp_secret(secret)
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

            set_rotation_verified(False)

            code = post_data.get("code")
            if isinstance(code, str) and code.strip():
                if await consume_configured_totp_code(self.config, code):
                    set_rotation_verified(True)
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
        self.config["dashboard"]["username"] = username
        set_dashboard_password_hashes(self.config, new_password)
        await set_password_storage_upgraded(self.db, self.config, True)
        await set_password_change_required(self.db, self.config, False)
        self.config.save_config()

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
        storage_upgraded = await is_password_storage_upgraded(self.db, self.config)
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
                verified_type = await verify_configured_2fa_code(
                    self.config,
                    totp_code,
                    allow_recovery=True,
                )
                if verified_type is TwoFactorCodeType.TOTP:
                    totp_verified = True
                elif verified_type is TwoFactorCodeType.RECOVERY:
                    self.config["dashboard"]["totp"] = {
                        "enable": False,
                        "secret": "",
                        "recovery_code_hash": "",
                    }
                    await revoke_user_trusted_devices(self.db)
                    self.config.save_config()
                elif len(totp_code) == 6 and totp_code.isdigit():
                    return self.error("TOTP 验证码无效", status_code=401)
                else:
                    return self.error("恢复码无效", status_code=401)

        change_pwd_hint = False
        md5_pwd_hint = is_md5_dashboard_password(password)
        password_change_required = await is_password_change_required(
            self.db,
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

        storage_upgraded = await is_password_storage_upgraded(self.db, self.config)
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
            self.db,
            self.config,
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
            set_dashboard_password_hashes(self.config, new_pwd)
            await set_password_storage_upgraded(self.db, self.config, True)
            await set_password_change_required(self.db, self.config, False)
            if is_totp_enabled(self.config):
                await revoke_user_trusted_devices(self.db)
        if username_to_save:
            self.config["dashboard"]["username"] = username_to_save

        self.config.save_config()

        return AuthServiceResult(message="Updated account successfully")

    def generate_jwt(self, username: str):
        payload = {
            "username": username,
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=7),
        }
        jwt_token = self.config["dashboard"].get("jwt_secret", None)
        if not jwt_token:
            raise ValueError("JWT secret is not set in the cmd_config.")
        return jwt.encode(payload, jwt_token, algorithm="HS256")

    async def is_setup_required(self) -> bool:
        if self.demo_mode:
            return False

        dashboard_config = self.config["dashboard"]
        password_change_required = await is_password_change_required(
            self.db,
            self.config,
        )
        if password_change_required:
            return True

        storage_upgraded = await is_password_storage_upgraded(self.db, self.config)
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
