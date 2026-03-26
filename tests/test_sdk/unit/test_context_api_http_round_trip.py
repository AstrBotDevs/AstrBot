# ruff: noqa: E402
"""HTTP 客户端 Core Bridge 集成测试。

测试覆盖 01_context_api.md 中 ctx.http 的所有方法：
- register_api(): 注册 API 端点
- unregister_api(): 注销 API 端点
- list_apis(): 列出当前插件注册的所有 API
"""
from __future__ import annotations

import pytest

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_http_client_round_trips_through_core_bridge(
    tmp_path, monkeypatch
):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    plugin_a_ctx = runtime.make_context("plugin-a")
    plugin_b_ctx = runtime.make_context("plugin-b")

    # plugin-a 注册 API
    await plugin_a_ctx.http.register_api(
        route="/api/v1/hello",
        methods=["GET", "POST"],
        handler_capability="plugin-a.hello_handler",
        description="Hello API",
    )
    await plugin_a_ctx.http.register_api(
        route="/api/v1/goodbye",
        methods=["DELETE"],
        handler_capability="plugin-a.goodbye_handler",
        description="Goodbye API",
    )

    # plugin-b 注册不同的 API
    await plugin_b_ctx.http.register_api(
        route="/api/v1/status",
        methods=["GET"],
        handler_capability="plugin-b.status_handler",
        description="Status API",
    )

    # 验证 plugin-a 的 API 列表
    plugin_a_apis = await plugin_a_ctx.http.list_apis()
    assert len(plugin_a_apis) == 2
    routes = {api["route"] for api in plugin_a_apis}
    assert routes == {"/api/v1/hello", "/api/v1/goodbye"}

    # 验证 plugin-b 的 API 列表
    plugin_b_apis = await plugin_b_ctx.http.list_apis()
    assert len(plugin_b_apis) == 1
    assert plugin_b_apis[0]["route"] == "/api/v1/status"

    # 注销 plugin-a 的一个 API
    await plugin_a_ctx.http.unregister_api(
        route="/api/v1/hello", methods=["GET", "POST"]
    )

    # 验证注销后的列表
    plugin_a_apis_after = await plugin_a_ctx.http.list_apis()
    assert len(plugin_a_apis_after) == 1
    assert plugin_a_apis_after[0]["route"] == "/api/v1/goodbye"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_http_register_api_normalizes_route(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 不带斜杠前缀的路由会被规范化
    await ctx.http.register_api(
        route="api/v1/test",
        methods=["GET"],
        handler_capability="plugin-a.test_handler",
        description="Test API",
    )

    apis = await ctx.http.list_apis()
    assert len(apis) == 1
    assert apis[0]["route"] == "/api/v1/test"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_http_unregister_without_methods_removes_all(
    tmp_path, monkeypatch
):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 注册同一路由的不同方法
    await ctx.http.register_api(
        route="/api/test",
        methods=["GET"],
        handler_capability="plugin-a.get",
        description="GET handler",
    )
    await ctx.http.register_api(
        route="/api/test",
        methods=["POST"],
        handler_capability="plugin-a.post",
        description="POST handler",
    )

    # 列出应该有两个条目
    apis = await ctx.http.list_apis()
    assert len(apis) == 2

    # 注销时指定方法，只删除指定方法
    await ctx.http.unregister_api(route="/api/test", methods=["GET"])

    apis_after = await ctx.http.list_apis()
    assert len(apis_after) == 1
    assert apis_after[0]["methods"] == ["POST"]
