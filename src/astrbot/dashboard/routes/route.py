from astrbot.core.config.astrbot_config import AstrBotConfig
from dataclasses import dataclass
from quart import Quart

@dataclass
class RouteContext:
    config: AstrBotConfig
    app: Quart

class Route:
    def __init__(self, context: RouteContext):
        self.app: Quart = context.app
        self.config: AstrBotConfig = context.config

    def register_routes(self):
        for route, (method, func) in self.routes.items():
            self.app.add_url_rule(f"/api{route}", view_func=func, methods=[method])

@dataclass
class Response:
    status: str | None = None
    message: str | None = None
    data: dict | None = None

    def error(self, message: str):
        self.status = "error"
        self.message = message
        return self

    def ok(self, data: dict = {}, message: str | None = None):
        self.status = "ok"
        self.data = data
        self.message = message
        return self
