import asyncio
import datetime

import jwt
from quart import jsonify, make_response, request

from astrbot import logger
from astrbot.core import DEMO_MODE

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
        if post_data["username"] == username and post_data["password"] == password:
            change_pwd_hint = False
            if (
                username == "astrbot"
                and password == "77b90590a8945a7d36c963981a307dc9"
                and not DEMO_MODE
            ):
                change_pwd_hint = True
                logger.warning("为了保证安全，请尽快修改默认密码。")
            token = self.generate_jwt(username)
            payload = Response().ok(
                {
                    "token": token,
                    "username": username,
                    "change_pwd_hint": change_pwd_hint,
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

        if post_data["password"] != password:
            return Response().error("原密码错误").__dict__

        new_pwd = post_data.get("new_password", None)
        new_username = post_data.get("new_username", None)
        if not new_pwd and not new_username:
            return Response().error("新用户名和新密码不能同时为空").__dict__

        # Verify password confirmation
        if new_pwd:
            confirm_pwd = post_data.get("confirm_password", None)
            if confirm_pwd != new_pwd:
                return Response().error("两次输入的新密码不一致").__dict__
            self.config["dashboard"]["password"] = new_pwd
        if new_username:
            self.config["dashboard"]["username"] = new_username

        self.config.save_config()

        return Response().ok(None, "修改成功").__dict__

    def generate_jwt(self, username):
        payload = {
            "username": username,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
        }
        jwt_token = self.config["dashboard"].get("jwt_secret", None)
        if not jwt_token:
            raise ValueError("JWT secret is not set in the cmd_config.")
        token = jwt.encode(payload, jwt_token, algorithm="HS256")
        return token

    @staticmethod
    def _set_dashboard_jwt_cookie(response, token: str) -> None:
        response.set_cookie(
            DASHBOARD_JWT_COOKIE_NAME,
            token,
            max_age=DASHBOARD_JWT_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Strict",
            secure=request.scheme == "https",
            path="/",
        )

    @staticmethod
    def _clear_dashboard_jwt_cookie(response) -> None:
        response.delete_cookie(
            DASHBOARD_JWT_COOKIE_NAME,
            httponly=True,
            samesite="Strict",
            secure=request.scheme == "https",
            path="/",
        )
