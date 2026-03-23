from dataclasses import dataclass

from quart import Quart

from astrbot.core.config.astrbot_config import AstrBotConfig


@dataclass
class RouteContext:
    config: AstrBotConfig
    app: Quart


class Route:
    routes: list | dict

    def __init__(self, context: RouteContext) -> None:
        self.app = context.app
        self.config = context.config

    def register_routes(self) -> None:
        def _add_rule(path, method, func) -> None:
            # 统一添加 /api 前缀
            full_path = f"/api{path}"
            endpoint = f"{self.__class__.__name__.lower()}_{func.__name__}"
            self.app.add_url_rule(full_path, view_func=func, methods=[method], endpoint=endpoint)

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

    def _serialize_value(self, value):
        # 将 AstrBotConfig dict 子类 转成 plain dict , 递归处理 dict/list
        from astrbot.core.config.astrbot_config import AstrBotConfig

        if isinstance(value, AstrBotConfig):
            # 明确构造 plain dict, 避免触发 AstrBotConfig.__init__
            return dict(value)
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._serialize_value(v) for v in value]
        # 如果还有其他自定义对象需要序列化, 可以在此扩展或抛出 TypeError
        return value

    def to_json(self):
        data = self.data if self.data is not None else {}
        return {
            "status": self.status,
            "message": self.message,
            "data": self._serialize_value(data),
        }
