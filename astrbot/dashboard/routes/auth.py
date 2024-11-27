from .route import Route, Response
from quart import Quart, request
from core.config.astrbot_config import AstrBotConfig

class AuthRoute(Route):
    def __init__(self, config: AstrBotConfig, app: Quart) -> None:
        super().__init__(config, app)
        self.routes = {
            '/auth/login': ('POST', self.login),
            '/auth/password/reset': ('POST', self.reset_password),
        }
        self.register_routes()
    
    async def login(self):
        username = self.config.dashboard.username
        password = self.config.dashboard.password
        post_data = await request.json
        if post_data["username"] == username and post_data["password"] == password:
            return Response().ok({
                "token": "astrbot-test-token",
                "username": username
            }).__dict__
        else:
            return Response().error("用户名或密码错误").__dict__
        
    async def reset_password(self):
        password = self.config.dashboard.password
        post_data = await request.json
        if post_data["password"] == password:
            self.config.dashboard.password = post_data['new_password']
            return Response().ok(None).__dict__
        else:
            return Response().error("原密码错误").__dict__