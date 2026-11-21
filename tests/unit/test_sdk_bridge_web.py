from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from astrbot.api.web import PluginRequest, bind_request_context
from astrbot.core.star.sdk_bridge import SDKPluginBridge
from tests.unit.test_sdk_bridge import FakeKVStore


def write_sdk_web_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "name": f"plugin_{plugin_root.name}",
                "desc": "web bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:TestPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {"required": [{"id": "web.route"}]},
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(
        """
from astrbot_sdk import Plugin


class TestPlugin(Plugin):
    def __init__(self, ctx):
        super().__init__(ctx)

        @self.ctx.web.route("/plugin/items/<item_id>", methods=["GET"])
        async def get_item(request, item_id: str):
            return {"id": item_id, "user": request.username}

        @self.ctx.web.route("/plugin/echo-auth", methods=["GET"])
        async def echo_auth(request):
            return {
                "authorization": request.headers.get("authorization", ""),
                "cookie": request.headers.get("cookie", ""),
            }
""",
        "utf-8",
    )


class FakeStarletteRequest:
    """Minimal starlette-Request stand-in for PluginRequest."""

    def __init__(self) -> None:
        self.method = "GET"
        self.headers = {
            "cookie": "session=SECRET",
            "x-custom": "keep",
        }
        self.cookies = {"session": "SECRET"}
        self.url = type("URL", (), {"path": "/plugin/items/abc", "query": ""})()
        self.client = None
        self.query_params = self

    def multi_items(self):
        return [("verbose", "yes")]

    async def body(self) -> bytes:
        return b""


@pytest.mark.asyncio
async def test_bridge_web_route_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "webbridge"
    write_sdk_web_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    context = MagicMock()
    context.registered_web_apis = []
    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()
        assert len(context.registered_web_apis) == 2
        route, view_handler, methods, desc = context.registered_web_apis[0]
        assert route == "/plugin/items/<item_id>"
        assert methods == ["GET"]

        plugin_request = PluginRequest(
            FakeStarletteRequest(),
            path_params={"item_id": "abc"},
            plugin_name="plugin_webbridge",
            username="admin",
        )
        with bind_request_context(plugin_request):
            response = await view_handler(item_id="abc")
        assert response.status_code == 200
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        import json

        assert json.loads(body) == {"id": "abc", "user": "admin"}
    finally:
        await bridge.stop()

    assert context.registered_web_apis == []


@pytest.mark.asyncio
async def test_bridge_web_route_swaps_authorization_for_scoped_view_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dashboard credential never crosses to the plugin; it is swapped
    for a plugin-scoped plugin_page_asset token that view scripts may echo
    into asset_token URLs."""
    import jwt

    from astrbot.dashboard.plugin_page_auth import PluginPageAuth

    plugin_root = tmp_path / "webbridge"
    write_sdk_web_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    context = MagicMock()
    context.registered_web_apis = []
    context.get_config.return_value = {"dashboard": {"jwt_secret": "view-secret"}}
    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()
        view_handler = next(
            api[1]
            for api in context.registered_web_apis
            if api[0] == "/plugin/echo-auth"
        )

        class AuthRequest(FakeStarletteRequest):
            def __init__(self) -> None:
                super().__init__()
                self.headers = {
                    "authorization": "Bearer DASHBOARD_ADMIN_JWT",
                    "cookie": "session=SECRET",
                }

        plugin_request = PluginRequest(
            AuthRequest(),
            path_params={},
            plugin_name="plugin_webbridge",
            username="admin",
        )
        with bind_request_context(plugin_request):
            response = await view_handler()
        assert response.status_code == 200
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        import json

        echoed = json.loads(body)
        assert echoed["cookie"] == ""
        forwarded = echoed["authorization"]
        assert forwarded.startswith("Bearer ")
        assert forwarded != "Bearer DASHBOARD_ADMIN_JWT"

        payload = jwt.decode(
            forwarded.removeprefix("Bearer "), "view-secret", algorithms=["HS256"]
        )
        assert payload["token_type"] == "plugin_page_asset"
        assert payload["plugin_name"] == "plugin_webbridge"
        assert payload["page_name"] == "*"
        assert payload["username"] == "admin"
        assert payload["exp"] - payload["iat"] == 7 * 24 * 60 * 60

        # The auth middleware only guards the shared bridge SDK script now;
        # view assets authenticate via path tokens at the v1 route layer.
        assert PluginPageAuth.is_scope_valid(
            payload, "/api/plugin/page/bridge-sdk.js"
        )
        assert not PluginPageAuth.is_scope_valid(
            payload, "/api/plugin/page/content/plugin_webbridge/app/index.html"
        )
        assert not PluginPageAuth.is_scope_valid(payload, "/api/auth/me")
    finally:
        await bridge.stop()


@pytest.mark.asyncio
async def test_bridge_web_route_drops_authorization_without_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a usable jwt secret the dashboard credential is dropped."""
    plugin_root = tmp_path / "webbridge"
    write_sdk_web_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    context = MagicMock()
    context.registered_web_apis = []
    context.get_config.return_value = {"dashboard": {}}
    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()
        view_handler = next(
            api[1]
            for api in context.registered_web_apis
            if api[0] == "/plugin/echo-auth"
        )

        class AuthRequest(FakeStarletteRequest):
            def __init__(self) -> None:
                super().__init__()
                self.headers = {"authorization": "Bearer DASHBOARD_ADMIN_JWT"}

        plugin_request = PluginRequest(
            AuthRequest(),
            path_params={},
            plugin_name="plugin_webbridge",
            username="admin",
        )
        with bind_request_context(plugin_request):
            response = await view_handler()
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        import json

        assert json.loads(body)["authorization"] == ""
    finally:
        await bridge.stop()
