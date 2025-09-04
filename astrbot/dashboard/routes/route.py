from astrbot.core.config.astrbot_config import AstrBotConfig
from dataclasses import dataclass
from quart import Quart


@dataclass
class RouteContext:
    config: AstrBotConfig
    app: Quart


class Route:
    def __init__(self, context: RouteContext):
        self.app = context.app
        self.config = context.config

    def register_routes(self):
        for route, (method, func) in self.routes.items():
            self.app.add_url_rule(f"/api{route}", view_func=func, methods=[method])


@dataclass
class Response:
    status: str | None = None
    message: str | None = None
    data: dict | list | None = None

    def error(self, message: str):
        self.status = "error"
        self.message = message
        return self

    def ok(self, data: dict | list | None = None, message: str | None = None):
        self.status = "ok"
        if data is None:
            data = {}
        self.data = data
        self.message = message
        return self
