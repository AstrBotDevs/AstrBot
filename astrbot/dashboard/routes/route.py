from dataclasses import dataclass

from fastapi import FastAPI

from astrbot.core.config.astrbot_config import AstrBotConfig


@dataclass
class RouteContext:
    config: AstrBotConfig
    app: FastAPI


class Route:
    def __init__(self, context: RouteContext):
        self.app = context.app
        self.config = context.config

    def register_routes(self):
        def _add_rule(path, method, func):
            # 统一添加 /api 前缀
            full_path = f"/api{path}"
            if method.upper() == "GET":
                self.app.get(full_path)(func)
            elif method.upper() == "POST":
                self.app.post(full_path)(func)
            elif method.upper() == "PUT":
                self.app.put(full_path)(func)
            elif method.upper() == "DELETE":
                self.app.delete(full_path)(func)
            elif method.upper() == "PATCH":
                self.app.patch(full_path)(func)

        # 兼容字典和列表两种格式
        routes_to_register = (
            self.routes.items() if isinstance(self.routes, dict) else self.routes
        )

        for route, definition in routes_to_register:
            # 兼容一个路由多个方法
            if isinstance(definition, list):
                for method, func in definition:
                    _add_rule(route, method, func)
            else:
                method, func = definition
                _add_rule(route, method, func)


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
