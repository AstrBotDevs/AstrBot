import datetime
import uuid

import anyio
import jwt
from fastapi import Body
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher
from pydantic import BaseModel

from astrbot import logger
from astrbot.core import DEMO_MODE

from .route import Response, Route, RouteContext


class LoginRequest(BaseModel):
    username: str
    password: str


class EditAccountRequest(BaseModel):
    password: str
    new_password: str | None = None
    new_username: str | None = None


class AuthRoute(Route):
    def __init__(self, context: RouteContext, fastapi_users, auth_backend) -> None:
        super().__init__(context)
        self.fastapi_users = fastapi_users
        self.auth_backend = auth_backend
        # Initialize password hasher for verifying MD5 passwords
        self.password_hash = PasswordHash((Argon2Hasher(),))

        # Register custom login route (legacy compatibility)
        self.routes = {
            "/auth/account/edit": ("POST", self.edit_account),
        }
        self.register_routes()

        # Register legacy login endpoint
        @self.app.post("/api/auth/login")
        async def legacy_login(login_data: LoginRequest):
            return await self.login(login_data)

    async def login(self, login_data: LoginRequest):
        """Legacy login endpoint for backward compatibility.

        The password from frontend is already MD5 hashed.
        We treat this MD5 value as the "password" and verify it against
        the stored Argon2 hash (which was created by hashing the MD5 value).
        """
        username = self.config["dashboard"]["username"]
        stored_password_hash = self.config["dashboard"]["password"]

        # Check if username matches
        if login_data.username != username:
            await anyio.sleep(3)
            return Response.error("用户名或密码错误")

        # The password from frontend is already MD5 hashed
        # Treat this MD5 value as the password for verification
        password_from_frontend = login_data.password

        # Verify using pwdlib's Argon2
        try:
            is_valid, new_hash = self.password_hash.verify_and_update(
                password_from_frontend, stored_password_hash
            )
            if not is_valid:
                await anyio.sleep(3)
                return Response.error("用户名或密码错误")

            # Update hash if needed (e.g., if algorithm parameters changed)
            if new_hash is not None:
                self.config["dashboard"]["password"] = new_hash
                self.config.save_config()
        except UnknownHashError:
            # Old password format detected - need to migrate
            # Hash the frontend password with Argon2 and save it
            logger.warning("检测到旧密码格式，正在迁移到新格式。首次登录后密码将更新。")
            new_hash = self.password_hash.hash(password_from_frontend)
            self.config["dashboard"]["password"] = new_hash
            self.config.save_config()
            logger.info("密码已迁移到 Argon2 格式")

        # Check if using default password (check against known default hash)
        change_pwd_hint = False
        # Note: This check is now done by comparing against the stored hash
        # If you need to detect default passwords, store the default hash separately
        if username == "astrbot" and not DEMO_MODE:
            # Simple heuristic: warn if it's the default username
            # More sophisticated check would require storing default password hash
            change_pwd_hint = True
            logger.warning("为了保证安全，请尽快修改默认密码。")

        # Generate token using the same JWT secret
        payload = {
            "username": username,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
            "sub": str(uuid.uuid4()),  # Add user ID for compatibility
        }
        jwt_secret = self.config["dashboard"].get("jwt_secret", None)
        if not jwt_secret:
            raise ValueError("JWT secret is not set in the cmd_config.")
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        return Response.ok(
            token=token,
            username=username,
            change_pwd_hint=change_pwd_hint,
        )

    async def edit_account(self, edit_data: EditAccountRequest = Body(...)):
        """Edit account endpoint.

        Passwords from frontend are MD5 hashed. We verify against the stored
        Argon2 hash and update with a new Argon2 hash if password is changed.
        """
        if DEMO_MODE:
            return Response.error("You are not permitted to do this operation in demo mode")

        stored_password_hash = self.config["dashboard"]["password"]
        # The password from frontend is already MD5 hashed
        provided_password = edit_data.password

        # Verify current password using pwdlib's Argon2
        try:
            is_valid = self.password_hash.verify(
                provided_password, stored_password_hash
            )
            if not is_valid:
                return Response.error("原密码错误")
        except UnknownHashError:
            # Old password format - migrate by creating new hash
            logger.warning("检测到旧密码格式，正在迁移...")
            # Create new hash from the provided password
            new_hash = self.password_hash.hash(provided_password)
            self.config["dashboard"]["password"] = new_hash
            # Continue with the account edit
            logger.info("密码已迁移到 Argon2 格式")

        if not edit_data.new_password and not edit_data.new_username:
            return Response.error("新用户名和新密码不能同时为空，你改了个寂寞")

        if edit_data.new_password:
            # Hash the new MD5 password with Argon2
            new_hash = self.password_hash.hash(edit_data.new_password)
            self.config["dashboard"]["password"] = new_hash
        if edit_data.new_username:
            self.config["dashboard"]["username"] = edit_data.new_username

        self.config.save_config()

        return Response.ok(None, "修改成功")
