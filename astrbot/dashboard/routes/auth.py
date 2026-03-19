import asyncio
import datetime

import jwt
from quart import request

from astrbot import logger
from astrbot.cli.commands.cmd_conf import (
    DEFAULT_DASHBOARD_PASSWORD_MD5,
    DEFAULT_DASHBOARD_PASSWORD_SHA256,
)
from astrbot.core import DEMO_MODE

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
        stored_password_hash = self.config["dashboard"]["password"]
        post_data = await request.json
        if post_data["username"] == username and self._matches_dashboard_password(
            stored_password_hash,
            post_data,
        ):
            change_pwd_hint = False
            if (
                username == "astrbot"
                and stored_password_hash
                in {DEFAULT_DASHBOARD_PASSWORD_MD5, DEFAULT_DASHBOARD_PASSWORD_SHA256}
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
        await asyncio.sleep(3)
        return Response().error("用户名或密码错误").__dict__

    async def edit_account(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        stored_password_hash = self.config["dashboard"]["password"]
        post_data = await request.json

        if not self._matches_dashboard_password(stored_password_hash, post_data):
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
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=7),
        }
        jwt_token = self.config["dashboard"].get("jwt_secret", None)
        if not jwt_token:
            raise ValueError("JWT secret is not set in the cmd_config.")
        token = jwt.encode(payload, jwt_token, algorithm="HS256")
        return token

    @staticmethod
    def _matches_dashboard_password(
        stored_password_hash: str,
        post_data: dict | None,
    ) -> bool:
        if not isinstance(post_data, dict):
            return False
        provided_hashes = {
            str(post_data.get("password", "") or "").strip().lower(),
            str(post_data.get("password_md5", "") or "").strip().lower(),
        }
        provided_hashes.discard("")
        return stored_password_hash in provided_hashes
