import datetime
import hashlib
import uuid

import jwt
from fastapi import Body
from pwdlib import PasswordHash
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
            await asyncio.sleep(3)
            return Response().error("用户名或密码错误").__dict__

        # The password from frontend is already MD5 hashed
        # Treat this MD5 value as the password for verification
        md5_password = login_data.password

        # Check if stored hash is old MD5 format (needs migration)
        # Old format: 32 character hex string (MD5)
        # New format: Argon2 hash (starts with $argon2)
        if len(stored_password_hash) == 32 and not stored_password_hash.startswith("$"):
            # Old MD5 format - compare directly and migrate
            provided_md5 = hashlib.md5(md5_password.encode()).hexdigest()
            if provided_md5 != stored_password_hash:
                await asyncio.sleep(3)
                return Response().error("用户名或密码错误").__dict__

            # Migrate to new format: hash the MD5 value with Argon2
            new_hash = self.password_hash.hash(md5_password)
            self.config["dashboard"]["password"] = new_hash
            self.config.save_config()
            logger.info("Migrated password from MD5 to Argon2 hash")
        else:
            # New Argon2 format - verify using pwdlib
            is_valid, new_hash = self.password_hash.verify_and_update(
                md5_password, stored_password_hash
            )
            if not is_valid:
                await asyncio.sleep(3)
                return Response().error("用户名或密码错误").__dict__

            # Update hash if needed (e.g., if algorithm parameters changed)
            if new_hash is not None:
                self.config["dashboard"]["password"] = new_hash
                self.config.save_config()

        # Check if using default password
        change_pwd_hint = False
        default_md5 = hashlib.md5(b"astrbot").hexdigest()
        if username == "astrbot" and md5_password == default_md5 and not DEMO_MODE:
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

        return (
            Response()
            .ok(
                {
                    "token": token,
                    "username": username,
                    "change_pwd_hint": change_pwd_hint,
                }
            )
            .__dict__
        )

    async def edit_account(self, edit_data: EditAccountRequest = Body(...)):
        """Edit account endpoint.

        Passwords from frontend are MD5 hashed. We verify against the stored
        Argon2 hash and update with a new Argon2 hash if password is changed.
        """
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        stored_password_hash = self.config["dashboard"]["password"]
        # The password from frontend is already MD5 hashed
        provided_md5_password = edit_data.password

        # Verify current password
        # Check if stored hash is old MD5 format
        if len(stored_password_hash) == 32 and not stored_password_hash.startswith("$"):
            # Old MD5 format
            provided_hash = hashlib.md5(provided_md5_password.encode()).hexdigest()
            if provided_hash != stored_password_hash:
                return Response().error("原密码错误").__dict__
        else:
            # New Argon2 format
            is_valid = self.password_hash.verify(
                provided_md5_password, stored_password_hash
            )
            if not is_valid:
                return Response().error("原密码错误").__dict__

        if not edit_data.new_password and not edit_data.new_username:
            return (
                Response().error("新用户名和新密码不能同时为空，你改了个寂寞").__dict__
            )

        if edit_data.new_password:
            # Hash the new MD5 password with Argon2
            new_hash = self.password_hash.hash(edit_data.new_password)
            self.config["dashboard"]["password"] = new_hash
        if edit_data.new_username:
            self.config["dashboard"]["username"] = edit_data.new_username

        self.config.save_config()

        return Response().ok(None, "修改成功").__dict__
