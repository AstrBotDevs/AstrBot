import asyncio
import datetime

import jwt
from quart import current_app, jsonify, make_response, request

from astrbot import logger
from astrbot.core import DEMO_MODE
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    is_default_dashboard_password,
    is_legacy_dashboard_password,
    validate_dashboard_password,
    verify_dashboard_password,
)

from .route import Response, Route, RouteContext

DASHBOARD_JWT_COOKIE_NAME = "astrbot_dashboard_jwt"
DASHBOARD_JWT_COOKIE_MAX_AGE = 7 * 24 * 60 * 60


class AuthRoute(Route):
    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.routes = {
            "/auth/login": ("POST", self.login),
            "/auth/logout": ("POST", self.logout),
            "/auth/account/edit": ("POST", self.edit_account),
        }
        self.register_routes()

    async def login(self):
        username = self.config["dashboard"]["username"]
        password = self.config["dashboard"]["password"]
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
            password_change_required = bool(
                self.config["dashboard"].get("password_change_required", False)
            )
            if (
                username == "astrbot"
                and is_default_dashboard_password(password)
                and not DEMO_MODE
            ):
                change_pwd_hint = True
                legacy_pwd_hint = True
                logger.warning("为了保证安全，请尽快修改默认密码。")
            if password_change_required and not DEMO_MODE:
                change_pwd_hint = True
            token = self.generate_jwt(username)
            if legacy_pwd_hint:
                self.config["dashboard"]["password"] = hash_dashboard_password(
                    req_password
                )
                self.config.save_config()
            payload = Response().ok(
                {
                    "token": token,
                    "username": username,
                    "change_pwd_hint": change_pwd_hint,
                    "legacy_pwd_hint": legacy_pwd_hint,
                },
            )
            response = await make_response(jsonify(payload.__dict__))
            self._set_dashboard_jwt_cookie(response, token)
            return response
        await asyncio.sleep(3)
        return Response().error("用户名或密码错误").__dict__

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

        password = self.config["dashboard"]["password"]
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
            self.config["dashboard"]["password"] = hash_dashboard_password(new_pwd)
            self.config["dashboard"]["password_change_required"] = False
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
