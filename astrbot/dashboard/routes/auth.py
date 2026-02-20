import asyncio
import datetime

import jwt
from quart import request

from astrbot import logger
from astrbot.core import DEMO_MODE, t

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
        if post_data["username"] == username and post_data["password"] == password:
            change_pwd_hint = False
            if (
                username == "astrbot"
                and password == "77b90590a8945a7d36c963981a307dc9"
                and not DEMO_MODE
            ):
                change_pwd_hint = True
                logger.warning(t("dashboard-auth-default-pwd-tip"))

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
        return Response().error(t("dashboard-auth-invalid-creds")).__dict__

    async def edit_account(self):
        if DEMO_MODE:
            return Response().error(t("dashboard-auth-demo-mode-denied")).__dict__

        password = self.config["dashboard"]["password"]
        post_data = await request.json

        if post_data["password"] != password:
            return Response().error(t("dashboard-auth-wrong-old-pwd")).__dict__

        new_pwd = post_data.get("new_password", None)
        new_username = post_data.get("new_username", None)
        if not new_pwd and not new_username:
            return Response().error(t("dashboard-auth-empty-fields")).__dict__

        if new_pwd:
            self.config["dashboard"]["password"] = new_pwd
        if new_username:
            self.config["dashboard"]["username"] = new_username

        self.config.save_config()

        return Response().ok(None, t("dashboard-auth-edit-success")).__dict__

    def generate_jwt(self, username):
        payload = {
            "username": username,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
        }
        jwt_token = self.config["dashboard"].get("jwt_secret", None)
        if not jwt_token:
            raise ValueError(t("dashboard-auth-jwt-secret-not-found"))
        token = jwt.encode(payload, jwt_token, algorithm="HS256")
        return token
