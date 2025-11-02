import asyncio
import hashlib
import uuid

from fastapi import Body
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
        """Legacy login endpoint for backward compatibility."""
        username = self.config["dashboard"]["username"]
        password_hash = self.config["dashboard"]["password"]

        # Hash the provided password (MD5 for legacy compatibility)
        provided_hash = hashlib.md5(login_data.password.encode()).hexdigest()

        if login_data.username == username and provided_hash == password_hash:
            change_pwd_hint = False
            if (
                username == "astrbot"
                and password_hash == "77b90590a8945a7d36c963981a307dc9"
                and not DEMO_MODE
            ):
                change_pwd_hint = True
                logger.warning("为了保证安全，请尽快修改默认密码。")

            # Generate token using the same JWT secret
            import datetime

            import jwt

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

        await asyncio.sleep(3)
        return Response().error("用户名或密码错误").__dict__

    async def edit_account(self, edit_data: EditAccountRequest = Body(...)):
        """Edit account endpoint."""
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        password_hash = self.config["dashboard"]["password"]
        provided_hash = hashlib.md5(edit_data.password.encode()).hexdigest()

        if provided_hash != password_hash:
            return Response().error("原密码错误").__dict__

        if not edit_data.new_password and not edit_data.new_username:
            return (
                Response().error("新用户名和新密码不能同时为空，你改了个寂寞").__dict__
            )

        if edit_data.new_password:
            new_hash = hashlib.md5(edit_data.new_password.encode()).hexdigest()
            self.config["dashboard"]["password"] = new_hash
        if edit_data.new_username:
            self.config["dashboard"]["username"] = edit_data.new_username

        self.config.save_config()

        return Response().ok(None, "修改成功").__dict__
