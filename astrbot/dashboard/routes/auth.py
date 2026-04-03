import asyncio
import datetime

import jwt
from quart import request

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


class AuthRoute(Route):
    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.routes = {
            "/auth/login": ("POST", self.login),
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

        if req_username == username and verify_dashboard_password(
            password, req_password
        ):
            change_pwd_hint = False
            legacy_pwd_hint = is_legacy_dashboard_password(password)
            if (
                username == "astrbot"
                and is_default_dashboard_password(password)
                and not DEMO_MODE
            ):
                change_pwd_hint = True
                logger.warning("检测到默认管理员凭据，请尽快修改密码。")
                legacy_pwd_hint = True

            return (
                Response()
                .ok(
                    {
                        "token": self.generate_jwt(username),
                        "username": username,
                        "change_pwd_hint": change_pwd_hint,
                        "legacy_pwd_hint": legacy_pwd_hint,
                    },
                )
                .__dict__
            )
        await asyncio.sleep(3)
        return Response().error("用户名或密码错误").__dict__

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
        if new_username:
            self.config["dashboard"]["username"] = new_username

        self.config.save_config()

        return Response().ok(None, "修改成功").__dict__

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
