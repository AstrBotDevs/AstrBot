from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Any

from quart import Quart, jsonify

from astrbot.core.config.astrbot_config import AstrBotConfig

if TYPE_CHECKING:
    from astrbot.core.core_lifecycle import AstrBotCoreLifecycle


RUNTIME_LOADING_MESSAGE = "Runtime is still loading. Please try again shortly."
RUNTIME_FAILED_MESSAGE = "Runtime bootstrap failed. Please check logs and retry."


def is_runtime_request_ready(core_lifecycle: "AstrBotCoreLifecycle") -> bool:
    return getattr(
        core_lifecycle, "runtime_request_ready", core_lifecycle.runtime_ready
    )


def get_runtime_guard_message(core_lifecycle: "AstrBotCoreLifecycle") -> str:
    failed = (
        core_lifecycle.runtime_failed
        or core_lifecycle.runtime_bootstrap_error is not None
    )
    return RUNTIME_FAILED_MESSAGE if failed else RUNTIME_LOADING_MESSAGE


def build_runtime_status_data(
    core_lifecycle: "AstrBotCoreLifecycle",
    *,
    include_failure_details: bool = True,
) -> dict[str, str | bool | None]:
    failure_message = None
    if include_failure_details and core_lifecycle.runtime_bootstrap_error is not None:
        failure_message = str(core_lifecycle.runtime_bootstrap_error)
    return {
        "state": core_lifecycle.lifecycle_state.value,
        "ready": is_runtime_request_ready(core_lifecycle),
        "failed": core_lifecycle.runtime_failed,
        "failure_message": failure_message,
    }


def runtime_status_response(
    core_lifecycle: "AstrBotCoreLifecycle",
    status_code: int = 503,
    *,
    include_failure_details: bool = True,
):
    message = get_runtime_guard_message(core_lifecycle)
    response = jsonify(
        Response(
            status="error",
            message=message,
            data=build_runtime_status_data(
                core_lifecycle,
                include_failure_details=include_failure_details,
            ),
        ).__dict__
    )
    response.status_code = status_code
    return response


def runtime_loading_response(
    core_lifecycle: "AstrBotCoreLifecycle",
    status_code: int = 503,
    *,
    include_failure_details: bool = True,
):
    return runtime_status_response(
        core_lifecycle,
        status_code=status_code,
        include_failure_details=include_failure_details,
    )


def guard_runtime_ready(core_lifecycle: "AstrBotCoreLifecycle", handler):
    @wraps(handler)
    async def wrapped(*args: Any, **kwargs: Any):
        if not is_runtime_request_ready(core_lifecycle):
            return runtime_status_response(core_lifecycle)
        return await handler(*args, **kwargs)

    return wrapped


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
            self.app.add_url_rule(
                full_path, view_func=func, methods=[method], endpoint=endpoint
            )

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
