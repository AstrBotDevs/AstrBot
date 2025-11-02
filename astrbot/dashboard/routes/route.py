from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar, overload

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from astrbot.core.config.astrbot_config import AstrBotConfig


@dataclass
class RouteContext:
    config: AstrBotConfig
    app: FastAPI


class Route:
    routes: dict[str, tuple[str, Any] | list[tuple[str, Any]]]

    def __init__(self, context: RouteContext):
        self.app = context.app
        self.config = context.config

    def register_routes(self):
        def _add_route(path, method, func):
            # 统一添加 /api 前缀
            full_path = f"/api{path}"
            methods = [method.upper()]
            self.app.add_api_route(full_path, func, methods=methods)

        # 兼容字典和列表两种格式
        routes_to_register = (
            self.routes.items()
            if hasattr(self, "routes") and isinstance(self.routes, dict)
            else getattr(self, "routes", [])
        )

        for route, definition in routes_to_register:
            # 兼容一个路由多个方法
            if isinstance(definition, list):
                for method, func in definition:
                    _add_route(route, method, func)
            else:
                method, func = definition
                _add_route(route, method, func)


DataT = TypeVar("DataT")


class Response(BaseModel, Generic[DataT]):
    status: Literal["ok", "error"] = "ok"
    message: str | None = None
    data: DataT | None = None

    # 两个重载:
    # 1) 调用者传入具体的 DataT,返回 Response[DataT]
    @overload
    @classmethod
    def ok(cls, data: DataT, message: str | None = "ok") -> Response[DataT]: ...

    # 2) 调用者使用 kwargs 构建匿名 dict 数据,返回 Response[dict[str, Any]]
    @overload
    @classmethod
    def ok(
        cls,
        data: None = None,
        message: str | None = "ok",
        **data_fields: object,
    ) -> Response[dict[str, object]]: ...

    @classmethod
    def ok(
        cls,
        data: Any | None = None,
        message: str | None = "ok",
        **data_fields: Any,
    ) -> Response[dict[str, Any]] | Response[DataT]:
        """创建一个成功响应(OK)...

        使用方式示例:
        - Response[LoginResponse].ok(LoginResponse(...))
        - Response[LoginResponse].ok({"username":..., "token": ...})
        - Response[LoginResponse].ok(username=..., token=...)
        """
        if data is None and data_fields:
            # 如果传入 kwargs,则把它们当作一个简单的 dict 作为 data
            data = dict(data_fields)
        return cls(status="ok", message=message, data=data)

    @classmethod
    def error(cls, message: str | None = "error") -> Response[DataT]:
        return cls(status="error", message=message, data=None)

    @staticmethod
    def sse(
        stream: AsyncIterable[str],
        headers: dict[str, str] | None = None,
    ) -> StreamingResponse:
        r"""用于返回标准 SSE 响应.
        stream: async 生成器,yield 每条 data: ...\n\n
        headers: 可选自定义响应头(如 Content-Type,Cache-Control 等).
        """
        default_headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
        }
        if headers:
            default_headers.update(headers)
        return StreamingResponse(stream, headers=default_headers)
