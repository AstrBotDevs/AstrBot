import asyncio
import datetime
import os

import jwt
import pyotp
from quart import current_app, g, jsonify, make_response, request

from astrbot import logger
from astrbot.core import DEMO_MODE
from astrbot.core.utils.auth_password import (
    is_default_dashboard_password,
    is_legacy_dashboard_password,
    validate_dashboard_password,
    verify_dashboard_password,
)
from astrbot.core.utils.totp import (
    TOTP_TRUSTED_DEVICE_COOKIE_NAME,
    TOTP_TRUSTED_DEVICE_MAX_AGE,
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

from .route import Response, Route, RouteContext

DASHBOARD_JWT_COOKIE_NAME = "astrbot_dashboard_jwt"
DASHBOARD_JWT_COOKIE_MAX_AGE = 7 * 24 * 60 * 60
SKIP_DEFAULT_PASSWORD_AUTH_ENV = "ASTRBOT_DASHBOARD_SKIP_DEFAULT_PASSWORD_AUTH"
SKIP_DEFAULT_PASSWORD_AUTH_ENV_LEGACY = "DASHBOARD_SKIP_DEFAULT_PASSWORD_AUTH"
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
LEGACY_PASSWORD_LOGIN_FAILURE_MESSAGE = (
    "Incorrect username or password. If you cannot log in after upgrading "
    "AstrBot even though the password is correct, see "
    "https://docs.astrbot.app/en/faq.html\n\n"
    "用户名或密码错误。如果你在升级 AstrBot 后遇到了密码正确但无法登录的情况，"
    "请参考 https://docs.astrbot.app/faq.html"
)


class AuthRoute(Route):
    def __init__(self, context: RouteContext, db) -> None:
        super().__init__(context)
        self.db = db
        self.routes = {
            "/auth/login": ("POST", self.login),
            "/auth/logout": ("POST", self.logout),
            "/auth/setup-status": ("GET", self.setup_status),
            "/auth/setup": ("POST", self.setup),
            "/auth/setup-authenticated": ("POST", self.setup_authenticated),
            "/auth/totp/setup": ("POST", self.totp_setup),
            "/auth/totp/recovery": ("POST", self.totp_recovery),
            "/auth/account/edit": ("POST", self.edit_account),
        }
        self.register_routes()

    async def setup_status(self):
        return (
            Response()
            .ok(
                {
                    "setup_required": await self._is_setup_required(),
                    "skip_default_password_auth": self._can_skip_default_password_auth(),
                    "password_upgrade_required": not await is_password_storage_upgraded(
                        self.db,
                        self.config,
                    ),
                }
            )
            .__dict__
        )

    async def totp_setup(self):
        post_data = await request.json

        if isinstance(post_data, dict) and post_data.get("secret"):
            secret = post_data["secret"]
            code = post_data.get("code")
            if not isinstance(secret, str) or not secret.strip():
                return Response().error("Invalid request payload").__dict__

            if not isinstance(code, str) or not code.strip():
                return Response().error("TOTP 验证码是必需的").__dict__
            if not await consume_totp_code(secret, code):
                return Response().error("TOTP 验证码无效").__dict__

            if is_totp_enabled(self.config) and not consume_rotation_verified():
                return Response().error("需要先验证当前 TOTP").__dict__

            set_pending_totp_secret(secret)
            recovery_code, recovery_code_hash = generate_recovery_code()
            return (
                Response()
                .ok(
                    {
                        "recovery_code": recovery_code,
                        "recovery_code_hash": recovery_code_hash,
                    },
                    "TOTP verified",
                )
                .__dict__
            )

        if is_totp_enabled(self.config):
            if not isinstance(post_data, dict):
                return Response().error("Invalid request payload").__dict__

            set_rotation_verified(False)

            code = post_data.get("code")
            if isinstance(code, str) and code.strip():
                if await consume_configured_totp_code(self.config, code):
                    set_rotation_verified(True)
                    return Response().ok({"secret": pyotp.random_base32()}).__dict__
                return Response().error("当前 TOTP 验证码无效").__dict__

            return Response().error("需要提供 TOTP 验证码或新密钥").__dict__

        return Response().ok({"secret": pyotp.random_base32()}).__dict__

    async def totp_recovery(self):
        # This endpoint MUST NOT persist the recovery code.
        recovery_code, recovery_code_hash = generate_recovery_code()
        return (
            Response()
            .ok(
                {
                    "recovery_code": recovery_code,
                    "recovery_code_hash": recovery_code_hash,
                }
            )
            .__dict__
        )

    async def setup(self):
        if not self._can_skip_default_password_auth():
            return Response().error("Setup without password is not enabled").__dict__
        if not await self._is_setup_required():
            return Response().error("Setup is not required").__dict__

        return await self._complete_setup()

    async def setup_authenticated(self):
        if not await self._is_setup_required():
            return Response().error("Setup is not required").__dict__
        if not isinstance(getattr(g, "username", None), str):
            return Response().error("未授权").__dict__

        return await self._complete_setup()

    async def _complete_setup(self):
        post_data = await request.json
        if not isinstance(post_data, dict):
            return Response().error("Invalid request payload").__dict__

        new_username = post_data.get("username")
        new_password = post_data.get("password")
        confirm_password = post_data.get("confirm_password")
        if not isinstance(new_username, str) or len(new_username.strip()) < 3:
            return Response().error("用户名长度至少3位").__dict__
        if not isinstance(new_password, str):
            return Response().error("新密码无效").__dict__
        if not isinstance(confirm_password, str) or confirm_password != new_password:
            return Response().error("两次输入的新密码不一致").__dict__

        try:
            validate_dashboard_password(new_password)
        except ValueError as e:
            return Response().error(str(e)).__dict__

        username = new_username.strip()
        self.config["dashboard"]["username"] = username
        set_dashboard_password_hashes(self.config, new_password)
        await set_password_storage_upgraded(self.db, self.config, True)
        await set_password_change_required(self.db, self.config, False)
        self.config.save_config()

        token = self.generate_jwt(username)
        payload = Response().ok(
            {
                "token": token,
                "username": username,
                "change_pwd_hint": False,
                "legacy_pwd_hint": False,
                "password_upgrade_required": False,
            },
            "Setup completed successfully",
        )
        response = await make_response(jsonify(payload.__dict__))
        self._set_dashboard_jwt_cookie(response, token)
        return response

    async def login(self):
        username = self.config["dashboard"]["username"]
        storage_upgraded = await is_password_storage_upgraded(self.db, self.config)
        password = get_dashboard_password_hash(self.config, upgraded=storage_upgraded)
        post_data = await request.json

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
            return Response().error("Invalid request payload").__dict__

        login_verified = req_username == username and verify_dashboard_password(
            password, req_password
        )

        if not login_verified:
            await asyncio.sleep(3)
            if req_password == "astrbot":
                return Response().error(DEFAULT_PASSWORD_LOGIN_FAILURE_MESSAGE).__dict__
            if is_legacy_dashboard_password(password):
                return Response().error(LEGACY_PASSWORD_LOGIN_FAILURE_MESSAGE).__dict__
            return await self._error_response(
                "用户名或密码错误",
                401,
            )

        totp_verified = False

        if is_totp_enabled(self.config):
            cookie_token = request.cookies.get(
                TOTP_TRUSTED_DEVICE_COOKIE_NAME, ""
            ).strip()
            if not await is_totp_trusted_device_valid(
                self.config, self.db, cookie_token
            ):
                if not isinstance(totp_code, str) or not totp_code.strip():
                    response = await make_response(
                        jsonify(
                            {
                                "status": "error",
                                "message": "需要 TOTP 验证",
                                "data": {"totp_required": True},
                            }
                        )
                    )
                    response.status_code = 401
                    return response
                verified_type = await verify_configured_2fa_code(
                    self.config, totp_code, allow_recovery=True
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
                    return await self._error_response("TOTP 验证码无效", 401)
                else:
                    return await self._error_response("恢复码无效", 401)

        change_pwd_hint = False
        legacy_pwd_hint = is_legacy_dashboard_password(password)
        password_change_required = await is_password_change_required(
            self.db,
            self.config,
        )
        if (
            storage_upgraded
            and username == "astrbot"
            and is_default_dashboard_password(password)
            and not DEMO_MODE
        ):
            change_pwd_hint = True
            legacy_pwd_hint = True
            logger.warning("为了保证安全，请尽快修改默认密码。")
        if password_change_required and not DEMO_MODE:
            change_pwd_hint = True
        token = self.generate_jwt(username)
        login_data = {
            "token": token,
            "username": username,
            "change_pwd_hint": change_pwd_hint,
            "legacy_pwd_hint": legacy_pwd_hint,
            "password_upgrade_required": not storage_upgraded,
        }
        payload = Response().ok(login_data)
        response = await make_response(jsonify(payload.__dict__))
        self._set_dashboard_jwt_cookie(response, token)

        if totp_verified and trust_device_flag:
            raw_token = await issue_totp_trusted_device(self.config, self.db)
            if raw_token:
                response.set_cookie(
                    TOTP_TRUSTED_DEVICE_COOKIE_NAME,
                    raw_token,
                    max_age=TOTP_TRUSTED_DEVICE_MAX_AGE,
                    httponly=True,
                    samesite="Strict",
                    secure=AuthRoute._use_secure_dashboard_jwt_cookie(),
                    path="/api/auth",
                )
        return response

    async def logout(self):
        response = await make_response(
            jsonify(Response().ok(None, "已退出登录").__dict__)
        )
        self._clear_dashboard_jwt_cookie(response)
        return response

    async def edit_account(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        storage_upgraded = await is_password_storage_upgraded(self.db, self.config)
        password = get_dashboard_password_hash(self.config, upgraded=storage_upgraded)
        post_data = await request.json
        if not isinstance(post_data, dict):
            return Response().error("Invalid request payload").__dict__

        req_password = post_data.get("password")
        if not isinstance(req_password, str):
            return Response().error("Invalid request payload").__dict__

        if not verify_dashboard_password(password, req_password):
            return Response().error("原密码错误").__dict__

        new_pwd = post_data.get("new_password", None)
        new_username = post_data.get("new_username", None)
        password_change_required = await is_password_change_required(
            self.db,
            self.config,
        )
        if (not storage_upgraded or password_change_required) and not new_pwd:
            return Response().error("请设置新密码以完成安全升级").__dict__
        if not new_pwd and not new_username:
            return Response().error("新用户名和新密码不能同时为空").__dict__

        # Verify password confirmation
        if new_pwd:
            if not isinstance(new_pwd, str):
                return Response().error("新密码无效").__dict__
            confirm_pwd = post_data.get("confirm_password", None)
            if not isinstance(confirm_pwd, str) or confirm_pwd != new_pwd:
                return Response().error("两次输入的新密码不一致").__dict__
            try:
                validate_dashboard_password(new_pwd)
            except ValueError as e:
                return Response().error(str(e)).__dict__
            set_dashboard_password_hashes(self.config, new_pwd)
            await set_password_storage_upgraded(self.db, self.config, True)
            await set_password_change_required(self.db, self.config, False)
            if is_totp_enabled(self.config):
                await revoke_user_trusted_devices(self.db)
        if new_username:
            self.config["dashboard"]["username"] = new_username

        self.config.save_config()

        return Response().ok(None, "Updated account successfully").__dict__

    def generate_jwt(self, username):
        payload = {
            "username": username,
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=7),
        }
        jwt_token = self.config["dashboard"].get("jwt_secret", None)
        if not jwt_token:
            raise ValueError("JWT secret is not set in the cmd_config.")
        token = jwt.encode(payload, jwt_token, algorithm="HS256")
        return token

    async def _is_setup_required(self) -> bool:
        if DEMO_MODE:
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

    @staticmethod
    async def _error_response(message: str, status_code: int):
        response = await make_response(jsonify(Response().error(message).__dict__))
        response.status_code = status_code
        return response

    def _can_skip_default_password_auth(self) -> bool:
        if not self._env_flag_enabled(SKIP_DEFAULT_PASSWORD_AUTH_ENV):
            return False
        host = (
            os.environ.get("DASHBOARD_HOST")
            or os.environ.get("ASTRBOT_DASHBOARD_HOST")
            or self.config["dashboard"].get("host", "")
        )
        return str(host).strip().lower() in LOCAL_DASHBOARD_HOSTS

    @staticmethod
    def _env_flag_enabled(name: str) -> bool:
        value = os.environ.get(name)
        if value is None and name == SKIP_DEFAULT_PASSWORD_AUTH_ENV:
            value = os.environ.get(SKIP_DEFAULT_PASSWORD_AUTH_ENV_LEGACY)
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _use_secure_dashboard_jwt_cookie() -> bool:
        return bool(
            current_app.config.get(
                "DASHBOARD_JWT_COOKIE_SECURE",
                not current_app.debug and not current_app.testing,
            )
        )

    @staticmethod
    def _set_dashboard_jwt_cookie(response, token: str) -> None:
        response.set_cookie(
            DASHBOARD_JWT_COOKIE_NAME,
            token,
            max_age=DASHBOARD_JWT_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Strict",
            secure=AuthRoute._use_secure_dashboard_jwt_cookie(),
            path="/",
        )

    @staticmethod
    def _clear_dashboard_jwt_cookie(response) -> None:
        response.delete_cookie(
            DASHBOARD_JWT_COOKIE_NAME,
            httponly=True,
            samesite="Strict",
            secure=AuthRoute._use_secure_dashboard_jwt_cookie(),
            path="/",
        )
