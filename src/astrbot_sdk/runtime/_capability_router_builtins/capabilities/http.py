from __future__ import annotations

import re
from typing import Any

from ....errors import AstrBotError
from ..bridge_base import CapabilityRouterBridgeBase

# 路由只允许字母、数字、/, -, _, . 以及路径参数 {param}，且必须以 / 开头。
# 参数段必须完整地形如 {param}，同时禁止空段（例如连续斜杠）。
_ROUTE_SEGMENT_RE = re.compile(r"^(?:[\w\-._]+|\{[\w\-._]+\})$")


def _validate_route(route: str, capability_name: str) -> None:
    """校验 HTTP 路由路径格式，阻止路径遍历和非法字符。"""
    if ".." in route:
        raise AstrBotError.invalid_input(f"{capability_name}: 路由路径不允许包含 '..'")
    if not route.startswith("/"):
        raise AstrBotError.invalid_input(
            f"{capability_name}: 路由路径格式非法，只允许字母/数字/-/_/./{{param}} 段，"
            "且必须以 / 开头，如 /foo/bar"
        )
    if route == "/":
        return
    segments = route.split("/")[1:]
    if any(
        not segment or not _ROUTE_SEGMENT_RE.fullmatch(segment) for segment in segments
    ):
        raise AstrBotError.invalid_input(
            f"{capability_name}: 路由路径格式非法，只允许字母/数字/-/_/./{{param}} 段，"
            "禁止连续斜杠，且必须以 / 开头，如 /foo/bar"
        )


class HttpCapabilityMixin(CapabilityRouterBridgeBase):
    async def _http_register_api(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        methods_payload = payload.get("methods")
        if not isinstance(methods_payload, list) or not all(
            isinstance(item, str) for item in methods_payload
        ):
            raise AstrBotError.invalid_input(
                "http.register_api 的 methods 必须是 string 数组"
            )
        route = str(payload.get("route", "")).strip()
        handler_capability = str(payload.get("handler_capability", "")).strip()
        if not route or not handler_capability:
            raise AstrBotError.invalid_input(
                "http.register_api 需要 route 和 handler_capability"
            )
        _validate_route(route, "http.register_api")
        plugin_name = self._require_caller_plugin_id("http.register_api")
        methods = sorted({method.upper() for method in methods_payload if method})
        entry: dict[str, Any] = {
            "route": route,
            "methods": methods,
            "handler_capability": handler_capability,
            "description": str(payload.get("description", "")),
            "plugin_id": plugin_name,
        }
        self.http_api_store = [
            item
            for item in self.http_api_store
            if not (
                item.get("route") == route
                and item.get("plugin_id") == entry["plugin_id"]
                and item.get("methods") == methods
            )
        ]
        self.http_api_store.append(entry)
        return {}

    async def _http_unregister_api(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        route = str(payload.get("route", "")).strip()
        methods_payload = payload.get("methods")
        if not isinstance(methods_payload, list) or not all(
            isinstance(item, str) for item in methods_payload
        ):
            raise AstrBotError.invalid_input(
                "http.unregister_api 的 methods 必须是 string 数组"
            )
        plugin_name = self._require_caller_plugin_id("http.unregister_api")
        methods = {method.upper() for method in methods_payload if method}
        updated: list[dict[str, Any]] = []
        for entry in self.http_api_store:
            if entry.get("route") != route:
                updated.append(entry)
                continue
            if entry.get("plugin_id") != plugin_name:
                updated.append(entry)
                continue
            if not methods:
                # `HTTPClient.unregister_api(methods=None)` 会归一化为空列表，
                # 公开语义就是“移除当前插件在该 route 下注册的全部方法”。
                continue
            remaining_methods = [
                method for method in entry.get("methods", []) if method not in methods
            ]
            if remaining_methods:
                updated.append({**entry, "methods": remaining_methods})
        self.http_api_store = updated
        return {}

    async def _http_list_apis(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_name = self._require_caller_plugin_id("http.list_apis")
        apis = [
            dict(entry)
            for entry in self.http_api_store
            if entry.get("plugin_id") == plugin_name
        ]
        return {"apis": apis}

    def _register_http_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("http.register_api", "注册 HTTP 路由"),
            call_handler=self._http_register_api,
        )
        self.register(
            self._builtin_descriptor("http.unregister_api", "注销 HTTP 路由"),
            call_handler=self._http_unregister_api,
        )
        self.register(
            self._builtin_descriptor("http.list_apis", "列出 HTTP 路由"),
            call_handler=self._http_list_apis,
        )
