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
async def test_bridge_web_route_drops_dashboard_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dashboard credentials are stripped before crossing the Runner boundary."""
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
