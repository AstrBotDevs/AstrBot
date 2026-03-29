import asyncio
import datetime

import jwt
from quart import request

from astrbot.cli.commands.cmd_conf import (
    hash_dashboard_password_secure,
    is_dashboard_password_hash,
    verify_dashboard_password,
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

    def _is_password_set(self, stored_password_hash: str) -> bool:
        """
        Check if the password has been set (not empty and is a valid hash).
        """
        if not stored_password_hash:
            return False
        # Must be a valid argon2 or pbkdf2 hash
        return is_dashboard_password_hash(stored_password_hash)

    async def login(self):
        stored_username = self.config["dashboard"]["username"]
        stored_password_hash = self.config["dashboard"]["password"]
        post_data = await request.json
        input_username = post_data.get("username", "")
        input_password = post_data.get("password", "")

        # Security: Require non-empty credentials
        if not input_username or not input_password:
            return Response().error("用户名和密码不能为空").to_json()

        # Check if password has been configured via CLI
        if not self._is_password_set(stored_password_hash):
            await asyncio.sleep(3)
            return (
                Response()
                .error("管理员密码未设置，请先运行 'astrbot conf admin' 命令设置密码").to_json()
            )

        # Normal login flow - credentials must match stored admin account
        if input_username == stored_username and self._matches_dashboard_password(
            stored_password_hash,
            post_data,
        ):
            return (
                Response()
                .ok(
                    {
                        "token": self.generate_jwt(stored_username),
                        "username": stored_username,
                        "change_pwd_hint": False,
                    },
                ).to_json()
            )

        # Security: Don't reveal whether it's username or password error
        await asyncio.sleep(3)
        return Response().error("用户名或密码错误").to_json()

    async def edit_account(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode").to_json()
            )

        stored_password_hash = self.config["dashboard"]["password"]
        post_data = await request.json

        if not self._matches_dashboard_password(stored_password_hash, post_data):
            return Response().error("原密码错误").to_json()

        new_pwd = post_data.get("new_password", None)
        new_username = post_data.get("new_username", None)
        if not new_pwd and not new_username:
            return Response().error("新用户名和新密码不能同时为空").to_json()

        # Verify password confirmation
        if new_pwd:
            confirm_pwd = post_data.get("confirm_password", None)
            if confirm_pwd != new_pwd:
                return Response().error("两次输入的新密码不一致").to_json()
            # Hash the new password before storing to ensure backend and CLI use the same format
            try:
                new_hash = hash_dashboard_password_secure(new_pwd)
            except Exception as e:
                return Response().error(f"Failed to hash new password: {e}").to_json()
            self.config["dashboard"]["password"] = new_hash
        if new_username:
            self.config["dashboard"]["username"] = new_username

        self.config.save_config()

        return Response().ok(None, "修改成功").to_json()

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
        """
        Verify posted credentials against stored hash.

        Behavior:
        - If client provided plaintext `password`, use `verify_dashboard_password`
          which only supports Argon2 encoded hashes.
        """
        if not isinstance(post_data, dict):
            return False

        # The dashboard only accepts plaintext credentials over the transport
        # layer; the server is responsible for secure password verification.
        pwd_plain = str(post_data.get("password", "") or "")

        if pwd_plain:
            try:
                return verify_dashboard_password(pwd_plain, stored_password_hash)
            except Exception:
                # Do not crash authentication on unexpected verifier errors; treat as mismatch.
                return False

        return False
