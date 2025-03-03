import jwt
import datetime
from .route import Route, Response, RouteContext
from quart import request
from astrbot.core import WEBUI_SK


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
            return (
                Response()
                .ok({"token": self.generate_jwt(username), "username": username})
                .__dict__
            )
        else:
            return Response().error("用户名或密码错误").__dict__

    async def edit_account(self):
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
