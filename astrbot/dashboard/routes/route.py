from collections.abc import Callable
from dataclasses import dataclass

from quart import Quart

from astrbot.core.config.astrbot_config import AstrBotConfig


@dataclass
class RouteContext:
    config: AstrBotConfig
    app: Quart


class Route:
    routes: dict[
        str,
        tuple[str, Callable]
        | list[tuple[str, Callable]]
        | tuple[str, Callable, str]
        | list[tuple[str, Callable, str]],
    ]

    def __init__(self, context: RouteContext):
        self.app = context.app
        self.config = context.config

    def register_routes(self):
        def _add_rule(path, method, func, endpoint: str | None = None):
            # 统一添加 /api 前缀
            full_path = f"/api{path}"
            self.app.add_url_rule(
                full_path, view_func=func, methods=[method], endpoint=endpoint
            )

        for route, defi in self.routes.items():
            if isinstance(defi, list):
                for item in defi:
                    if len(item) == 2:
                        method, func = item
                        _add_rule(route, method, func)
                    elif len(item) == 3:
                        method, func, endpoint = item
                        _add_rule(route, method, func, endpoint)
            else:
                if len(defi) == 2:
                    method, func = defi
                    _add_rule(route, method, func)
                elif len(defi) == 3:
                    method, func, endpoint = defi
                    _add_rule(route, method, func, endpoint)


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
