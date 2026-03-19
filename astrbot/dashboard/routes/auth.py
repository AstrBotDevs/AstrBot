import asyncio
import datetime

import jwt
from quart import request

from astrbot import logger
from astrbot.cli.commands.cmd_conf import (
    DEFAULT_DASHBOARD_PASSWORD_MD5,
    DEFAULT_DASHBOARD_PASSWORD_SHA256,
    hash_dashboard_password_secure,
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
                logger.warning("为了保证安全,请尽快修改默认密码｡")

            # 自动迁移:如果后端当前存储的是 legacy hex(MD5 或 SHA256)的 digest,
            # 且客户端此次提交了明文密码并且明文能通过校验,则将其替换为安全哈希(argon2 或 pbkdf2 回退)｡
            try:
                pwd_plain = str(post_data.get("password", "") or "")
                s = str(stored_password_hash or "").strip().lower()
                is_legacy_hex = (len(s) == 32 or len(s) == 64) and all(
                    ch in "0123456789abcdef" for ch in s
                )
                if (
                    pwd_plain
                    and is_legacy_hex
                    and verify_dashboard_password(pwd_plain, stored_password_hash)
                ):
                    try:
                        new_hash = hash_dashboard_password_secure(pwd_plain)
                        self.config["dashboard"]["password"] = new_hash
                        # 保存到配置文件;如果保存失败只是记录警告但不阻止登录流程
                        try:
                            self.config.save_config()
                            logger.info("已将旧版密码迁移为安全哈希格式｡")
                        except Exception:
                            logger.warning("密码迁移:保存配置失败,迁移未持久化｡")
                    except Exception as e:
                        logger.warning(f"密码迁移失败(生成哈希时出错):{e}")
            except Exception:
                logger.exception("密码迁移过程中发生意外错误")

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
            # Hash the new password before storing to ensure backend and CLI use the same format
            try:
                new_hash = hash_dashboard_password_secure(new_pwd)
            except Exception as e:
                return Response().error(f"Failed to hash new password: {e}").__dict__
            self.config["dashboard"]["password"] = new_hash
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
        """
        Verify posted credentials against stored hash.

        Behavior:
        - If client provided plaintext `password`, use `verify_dashboard_password`
          which supports argon2, PBKDF2 fallback, and legacy hex digests.
        - If only `password_md5` (hex) is provided, accept only when the stored
          hash is the same legacy MD5 hex digest (backwards compatibility).
        """
        if not isinstance(post_data, dict):
            return False

        # Prefer plaintext verification when available
        pwd_plain = str(post_data.get("password", "") or "")
        pwd_md5 = str(post_data.get("password_md5", "") or "").strip().lower()

        if pwd_plain:
            try:
                return verify_dashboard_password(pwd_plain, stored_password_hash)
            except Exception:
                # Do not crash authentication on unexpected verifier errors; treat as mismatch.
                return False

        # If only MD5 hex supplied by client, accept only if stored hash is the same legacy MD5 hex.
        if pwd_md5:
            try:
                return (
                    isinstance(stored_password_hash, str)
                    and stored_password_hash.strip().lower() == pwd_md5
                )
            except Exception:
                return False

        return False
