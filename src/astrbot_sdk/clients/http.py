"""HTTP 客户端模块。

提供 HTTP API 注册能力。

功能说明：
    - 注册自定义 Web API 端点
    - 支持异步请求处理
    - 与宿主 Web 服务器集成

设计说明：
    由于跨进程架构，handler 函数无法直接序列化传递。
    插件需要先声明处理 HTTP 请求的 capability，然后注册路由到 capability 的映射。
    当前插件身份由运行时在协议层透传，客户端 payload 不暴露 `plugin_id`。

    调用流程:
        HTTP 请求 → 宿主 Web 服务器 → 查找 route 映射 → invoke capability → Worker 执行 handler → 返回响应

示例:
    # 插件声明处理 HTTP 请求的 capability
    @provide_capability(
        name="my_plugin.http_handler",
        description="处理 /my-api 的 HTTP 请求",
        input_schema={...},
        output_schema={...}
    )
    async def handle_http_request(request_id: str, payload: dict, cancel_token):
        return {"status": 200, "body": {"result": "ok"}}

    # 注册路由 → capability 映射
    await ctx.http.register_api(
        route="/my-api",
        methods=["GET", "POST"],
        handler_capability="my_plugin.http_handler",
        description="我的 API"
    )
"""

from __future__ import annotations

from typing import Any

from ..decorators import get_capability_meta
from ..errors import AstrBotError
from ._proxy import CapabilityProxy


def _resolve_handler_capability(
    handler_capability: str | None,
    handler: Any | None,
) -> str:
    if handler_capability and handler is not None:
        raise AstrBotError.invalid_input(
            "register_api 不能同时提供 handler_capability 和 handler",
            hint="请二选一：传 capability 名称字符串，或传 @provide_capability 标记的方法",
        )
    if handler_capability:
        return handler_capability
    if handler is None:
        raise AstrBotError.invalid_input(
            "register_api 需要提供 handler_capability 或 handler",
            hint="示例：handler_capability='demo.http_handler' 或 handler=self.http_handler_capability",
        )
    target = getattr(handler, "__func__", handler)
    meta = get_capability_meta(target)
    if meta is None:
        raise AstrBotError.invalid_input(
            "register_api(handler=...) 需要传入使用 @provide_capability 声明的方法",
            hint="请先用 @provide_capability(name='demo.http_handler', ...) 标记该方法",
        )
    return meta.descriptor.name


class HTTPClient:
    """HTTP 能力客户端。

    提供 Web API 注册能力，允许插件暴露自定义 HTTP 端点。

    Attributes:
        _proxy: CapabilityProxy 实例，用于远程能力调用
    """

    def __init__(self, proxy: CapabilityProxy) -> None:
        """初始化 HTTP 客户端。

        Args:
            proxy: CapabilityProxy 实例
        """
        self._proxy = proxy

    async def register_api(
        self,
        route: str,
        handler_capability: str | None = None,
        *,
        handler: Any | None = None,
        methods: list[str] | None = None,
        description: str = "",
    ) -> None:
        """注册 Web API 端点。

        Args:
            route: API 路由路径（如 "/my-api"）
            handler_capability: 处理此路由的 capability 名称
            handler: 使用 @provide_capability 标记的方法引用
            methods: HTTP 方法列表，默认 ["GET"]
            description: API 描述

        示例:
            await ctx.http.register_api(
                route="/my-api",
                handler_capability="my_plugin.http_handler",
                methods=["GET", "POST"],
                description="我的 API"
            )
        """
        if methods is None:
            methods = ["GET"]
        resolved_handler = _resolve_handler_capability(handler_capability, handler)

        await self._proxy.call(
            "http.register_api",
            {
                "route": route,
                "methods": methods,
                "handler_capability": resolved_handler,
                "description": description,
            },
        )

    async def unregister_api(
        self, route: str, methods: list[str] | None = None
    ) -> None:
        """注销 Web API 端点。

        Args:
            route: API 路由路径
            methods: HTTP 方法列表，None 表示所有方法

        示例:
            await ctx.http.unregister_api("/my-api")
        """
        if methods is None:
            methods = []

        await self._proxy.call(
            "http.unregister_api",
            {"route": route, "methods": methods},
        )

    async def list_apis(self) -> list[dict[str, Any]]:
        """列出当前插件注册的所有 API。

        Returns:
            API 列表，每项包含 route, methods, description

        示例:
            apis = await ctx.http.list_apis()
            for api in apis:
                print(f"{api['route']}: {api['methods']}")
        """
        output = await self._proxy.call(
            "http.list_apis",
            {},
        )
        return output.get("apis", [])
