import asyncio
import datetime

import jwt
from quart import request
from sqlmodel import col, select

from astrbot import logger
from astrbot.core import DEMO_MODE
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import WebUIUser

from .route import Response, Route, RouteContext


class AuthRoute(Route):
    def __init__(self, context: RouteContext, db: BaseDatabase) -> None:
        super().__init__(context)
        self.db = db
        self.routes = {
            "/auth/login": ("POST", self.login),
            "/auth/profile": ("GET", self.profile),
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

            return (
                Response()
                .ok(
                    {
                        "token": self.generate_jwt(username),
                        "username": username,
                        "change_pwd_hint": change_pwd_hint,
                    },
                )
                .__dict__
            )

        webui_user = await self._get_webui_user(post_data["username"])
        if (
            webui_user
            and webui_user.enabled
            and webui_user.password
            and post_data.get("password") == webui_user.password
        ):
            return (
                Response()
                .ok(
                    {
                        "token": self.generate_jwt(
                            webui_user.username,
                            role="webui_user",
                            user_id=webui_user.user_id,
                            scopes=[webui_user.scope],
                        ),
                        "username": webui_user.username,
                        "role": "webui_user",
                        "scopes": [webui_user.scope],
                        "permissions": {
                            "allowed_config_ids": webui_user.allowed_config_ids or [],
                            "allow_provider_management": webui_user.allow_provider_management,
                        },
                        "change_pwd_hint": False,
                    },
                )
                .__dict__
            )
        await asyncio.sleep(3)
        return Response().error("用户名或密码错误").__dict__

    async def profile(self):
        from quart import g

        role = g.get("webui_role", "admin")
        if role == "webui_user":
            user = g.get("webui_user")
            if not user:
                return Response().error("用户不存在或已禁用").__dict__
            return (
                Response()
                .ok(
                    {
                        "username": user.username,
                        "role": "webui_user",
                        "scopes": [user.scope],
                        "permissions": {
                            "allowed_config_ids": user.allowed_config_ids or [],
                            "allow_provider_management": user.allow_provider_management,
                        },
                    },
                )
                .__dict__
            )

        return (
            Response()
            .ok(
                {
                    "username": g.get("username", self.config["dashboard"]["username"]),
                    "role": "admin",
                    "scopes": ["*"],
                    "permissions": {
                        "allowed_config_ids": ["*"],
                        "allow_provider_management": True,
                    },
                },
            )
            .__dict__
        )

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

    async def _get_webui_user(self, username: str) -> WebUIUser | None:
        async with self.db.get_db() as session:
            result = await session.execute(
                select(WebUIUser).where(col(WebUIUser.username) == username)
            )
            return result.scalar_one_or_none()

    def generate_jwt(
        self,
        username,
        *,
        role: str = "admin",
        user_id: str | None = None,
        scopes: list[str] | None = None,
    ):
        payload = {
            "username": username,
            "role": role,
            "scopes": scopes or ["*"],
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=7),
        }
        if user_id:
            payload["user_id"] = user_id
        jwt_token = self.config["dashboard"].get("jwt_secret", None)
        if not jwt_token:
            raise ValueError("JWT secret is not set in the cmd_config.")
        token = jwt.encode(payload, jwt_token, algorithm="HS256")
        return token
