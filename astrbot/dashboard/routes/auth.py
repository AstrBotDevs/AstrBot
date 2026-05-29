import asyncio
import datetime
import os
import secrets
import time

import jwt
from quart import current_app, g, jsonify, make_response, request

from astrbot import logger
from astrbot.core import DEMO_MODE
from astrbot.core.config.astrbot_config import DASHBOARD_RESET_FLAG_FILE
from astrbot.core.utils.auth_password import (
    is_default_dashboard_password,
    is_legacy_dashboard_password,
    validate_dashboard_password,
    verify_dashboard_password,
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
    def __init__(self, context: RouteContext, db, core_lifecycle=None) -> None:
        super().__init__(context)
        self.db = db
        self.core_lifecycle = core_lifecycle
        # Password reset confirmation code state
        self._reset_code: str | None = None
        self._reset_code_expiry: float = 0.0
        self._reset_failed_attempts: int = 0
        # Rate limiting: list of recent attempt timestamps
        self._reset_attempts: list[float] = []
        self.routes = {
            "/auth/login": ("POST", self.login),
            "/auth/logout": ("POST", self.logout),
            "/auth/setup-status": ("GET", self.setup_status),
            "/auth/setup": ("POST", self.setup),
            "/auth/setup-authenticated": ("POST", self.setup_authenticated),
            "/auth/account/edit": ("POST", self.edit_account),
            "/auth/forgot-password": ("POST", self.forgot_password),
            "/auth/forgot-password/init": ("POST", self.forgot_password_init),
        }
        self.register_routes()

    def _generate_reset_code(self) -> str:
        """Generate a 6-digit alphanumeric confirmation code."""
        charset = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(charset) for _ in range(6))

    def _is_rate_limited(
        self, max_attempts: int = 3, window_seconds: float = 300.0
    ) -> bool:
        """Check if the forgot-password endpoint is rate-limited."""
        now = time.monotonic()
        # Keep only attempts within the time window
        self._reset_attempts = [
            t for t in self._reset_attempts if now - t < window_seconds
        ]
        return len(self._reset_attempts) >= max_attempts

    def _record_attempt(self) -> None:
        """Record a forgot-password attempt timestamp."""
        self._reset_attempts.append(time.monotonic())

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
        if not isinstance(req_username, str) or not isinstance(req_password, str):
            return Response().error("Invalid request payload").__dict__

        login_verified = req_username == username and verify_dashboard_password(
            password, req_password
        )

        if login_verified:
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
            payload = Response().ok(
                {
                    "token": token,
                    "username": username,
                    "change_pwd_hint": change_pwd_hint,
                    "legacy_pwd_hint": legacy_pwd_hint,
                    "password_upgrade_required": not storage_upgraded,
                },
            )
            response = await make_response(jsonify(payload.__dict__))
            self._set_dashboard_jwt_cookie(response, token)
            return response
        await asyncio.sleep(3)
        if req_password == "astrbot":
            return Response().error(DEFAULT_PASSWORD_LOGIN_FAILURE_MESSAGE).__dict__
        if is_legacy_dashboard_password(password):
            return Response().error(LEGACY_PASSWORD_LOGIN_FAILURE_MESSAGE).__dict__
        return Response().error("用户名或密码错误").__dict__

    async def logout(self):
        response = await make_response(
            jsonify(Response().ok(None, "已退出登录").__dict__)
        )
        self._clear_dashboard_jwt_cookie(response)
        return response

    async def forgot_password_init(self):
        """Generate a confirmation code and print it to the terminal."""
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        if self._is_rate_limited():
            return Response().error("请求过于频繁，请 5 分钟后再试").__dict__

        self._record_attempt()
        code = self._generate_reset_code()
        self._reset_code = code
        self._reset_code_expiry = time.monotonic() + 300.0  # 5 minutes
        self._reset_failed_attempts = 0

        logger.info(
            "Password reset requested. Confirmation code: %s "
            "(valid for 5 minutes). Enter this code in the WebUI to proceed.",
            code,
        )
        return (
            Response().ok(None, "确认码已生成，请查看终端日志获取 6 位确认码").__dict__
        )

    async def forgot_password(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.json
        if not isinstance(post_data, dict):
            return Response().error("Invalid request payload").__dict__

        code = post_data.get("code", "")
        if not isinstance(code, str) or len(code) != 6:
            return Response().error("确认码格式不正确").__dict__

        if self._reset_code is None:
            return Response().error("请先点击忘记密码获取确认码").__dict__

        if time.monotonic() > self._reset_code_expiry:
            self._reset_code = None
            return Response().error("确认码已过期，请重新获取").__dict__

        if code.upper() != self._reset_code.upper():
            self._reset_failed_attempts += 1
            if self._reset_failed_attempts >= 3:
                self._reset_code = None
                return Response().error("确认码错误次数过多，已失效，请重新获取").__dict__
            remaining = 3 - self._reset_failed_attempts
            return Response().error(f"确认码不正确，还可以尝试 {remaining} 次").__dict__

        # Clear the code after successful validation
        self._reset_code = None

        try:
            with open(DASHBOARD_RESET_FLAG_FILE, "w", encoding="utf-8") as f:
                f.write("1")
        except OSError as e:
            logger.error(f"Failed to create password reset flag file: {e}")
            return Response().error("创建重置标记失败，请检查文件权限").__dict__

        # Trigger restart asynchronously so the HTTP response can be sent first
        if self.core_lifecycle is not None:
            self._restart_task = asyncio.create_task(self._delayed_restart())

        return Response().ok(None, "密码重置请求已接受，AstrBot 即将重启").__dict__

    async def _delayed_restart(self, delay: float = 1.0) -> None:
        """Delay briefly to let the HTTP response finish, then restart."""
        await asyncio.sleep(delay)
        try:
            await self.core_lifecycle.restart()
        except Exception as e:
            logger.error(f"Auto-restart after password reset failed: {e}")

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
