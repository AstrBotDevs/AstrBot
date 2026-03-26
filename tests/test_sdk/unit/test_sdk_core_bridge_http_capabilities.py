# ruff: noqa: E402
from __future__ import annotations

import pytest

from astrbot_sdk.decorators import provide_capability

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


class _HTTPCapabilityOwner:
    @provide_capability(
        name="sdk-demo.http_handler",
        description="Handle demo HTTP requests",
    )
    async def handle_http_request(self, request_id: str, payload: dict, cancel_token):
        return {"status": 200, "body": {"request_id": request_id, "payload": payload}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_http_register_and_list_round_trip_via_handler_method(
    tmp_path,
    monkeypatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("sdk-demo")
    owner = _HTTPCapabilityOwner()

    await ctx.http.register_api(
        route="demo-api",
        handler=owner.handle_http_request,
        methods=["post", "GET"],
        description="Demo API",
    )

    assert await ctx.http.list_apis() == [
        {
            "route": "/demo-api",
            "methods": ["GET", "POST"],
            "handler_capability": "sdk-demo.http_handler",
            "description": "Demo API",
        }
    ]
    assert runtime.plugin_bridge.list_http_apis("sdk-demo") == [
        {
            "route": "/demo-api",
            "methods": ["GET", "POST"],
            "handler_capability": "sdk-demo.http_handler",
            "description": "Demo API",
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_http_unregister_preserves_plugin_scope_and_method_semantics(
    tmp_path,
    monkeypatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    plugin_a_ctx = runtime.make_context("plugin-a")
    plugin_b_ctx = runtime.make_context("plugin-b")

    await plugin_a_ctx.http.register_api(
        route="/shared",
        handler_capability="plugin-a.http_handler",
        methods=["GET", "POST"],
        description="Plugin A route",
    )
    await plugin_b_ctx.http.register_api(
        route="/shared",
        handler_capability="plugin-b.http_handler",
        methods=["GET"],
        description="Plugin B route",
    )

    await plugin_a_ctx.http.unregister_api("/shared", methods=["POST"])

    assert await plugin_a_ctx.http.list_apis() == [
        {
            "route": "/shared",
            "methods": ["GET"],
            "handler_capability": "plugin-a.http_handler",
            "description": "Plugin A route",
        },
    ]
    assert await plugin_b_ctx.http.list_apis() == [
        {
            "route": "/shared",
            "methods": ["GET"],
            "handler_capability": "plugin-b.http_handler",
            "description": "Plugin B route",
        }
    ]

    await plugin_a_ctx.http.unregister_api("/shared")

    assert await plugin_a_ctx.http.list_apis() == []
