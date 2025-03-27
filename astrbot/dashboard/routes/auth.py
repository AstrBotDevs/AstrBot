import jwt
import datetime
from .route import Route, Response, RouteContext
from quart import request
from astrbot.core import WEBUI_SK, DEMO_MODE
from astrbot import logger


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
            if username == "astrbot" and password == "77b90590a8945a7d36c963981a307dc9":
                change_pwd_hint = True
                logger.warning("为了保证安全，请尽快修改默认密码。")

            return (
                Response()
                .ok(
                    {
                        "token": self.generate_jwt(username),
                        "username": username,
                        "change_pwd_hint": change_pwd_hint,
                    }
                )
                .__dict__
            )
        else:
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

        if post_data["password"] != password:
            return Response().error("原密码错误").__dict__

        new_pwd = post_data.get("new_password", None)
        new_username = post_data.get("new_username", None)
        if not new_pwd and not new_username:
            return (
                Response().error("新用户名和新密码不能同时为空，你改了个寂寞").__dict__
            )

        if new_pwd:
            self.config["dashboard"]["password"] = new_pwd
        if new_username:
            self.config["dashboard"]["username"] = new_username

        self.config.save_config()

        return Response().ok(None, "修改成功").__dict__

    def generate_jwt(self, username):
        payload = {
            "username": username,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30),
        }
        token = jwt.encode(payload, WEBUI_SK, algorithm="HS256")
        return token
