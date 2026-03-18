# ruff: noqa: E402
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from astrbot_sdk.runtime.loader import (
    PluginSpec,
    load_plugin_config_schema,
)
from quart import Quart

from astrbot.dashboard.routes.config import ConfigRoute
from astrbot.dashboard.routes.route import RouteContext


class _FakePluginManager:
    def __init__(self) -> None:
        self.reloaded: list[str] = []

    async def reload(self, plugin_name: str | None = None) -> tuple[bool, str]:
        self.reloaded.append(str(plugin_name))
        return True, ""


class _FakeSdkBridge:
    def __init__(self) -> None:
        self.schemas: dict[str, dict[str, Any]] = {
            "sdk-demo": {
                "count": {
                    "type": "int",
                    "description": "counter",
                    "default": 1,
                }
            }
        }
        self.configs: dict[str, dict[str, Any]] = {"sdk-demo": {"count": 1}}
        self.saved: list[tuple[str, dict[str, Any]]] = []
        self.reloaded: list[str] = []

    def get_plugin_metadata(self, plugin_name: str) -> dict[str, Any] | None:
        if plugin_name not in self.schemas:
            return None
        return {"name": plugin_name, "runtime_kind": "sdk"}

    def get_plugin_config_schema(self, plugin_name: str) -> dict[str, Any] | None:
        schema = self.schemas.get(plugin_name)
        return dict(schema) if schema is not None else None

    def get_plugin_config(self, plugin_name: str) -> dict[str, Any] | None:
        config = self.configs.get(plugin_name)
        return dict(config) if config is not None else None

    def save_plugin_config(
        self,
        plugin_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        saved = dict(payload)
        self.configs[plugin_name] = saved
        self.saved.append((plugin_name, saved))
        return dict(saved)

    async def reload_plugin(self, plugin_name: str) -> None:
        self.reloaded.append(plugin_name)


def _build_config_route(
    *,
    sdk_bridge: _FakeSdkBridge | None = None,
) -> tuple[ConfigRoute, Quart, _FakePluginManager]:
    app = Quart(__name__)
    plugin_manager = _FakePluginManager()
    core_lifecycle = SimpleNamespace(
        astrbot_config=cast(Any, {}),
        astrbot_config_mgr=SimpleNamespace(confs={}),
        plugin_manager=plugin_manager,
        sdk_plugin_bridge=sdk_bridge,
        umop_config_router=SimpleNamespace(),
    )
    route = ConfigRoute(
        RouteContext(config=cast(Any, {}), app=app),
        core_lifecycle=cast(Any, core_lifecycle),
    )
    return route, app, plugin_manager


@pytest.mark.unit
def test_load_plugin_config_schema_logs_invalid_json(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    plugin_dir = tmp_path / "sdk_demo"
    plugin_dir.mkdir()
    schema_path = plugin_dir / "_conf_schema.json"
    schema_path.write_text('{"count": {"type": "int",},}', encoding="utf-8")

    plugin = PluginSpec(
        name="sdk-demo",
        plugin_dir=plugin_dir,
        manifest_path=plugin_dir / "plugin.yaml",
        requirements_path=plugin_dir / "requirements.txt",
        python_version="3.11",
        manifest_data={},
    )

    with caplog.at_level(logging.WARNING):
        schema = load_plugin_config_schema(plugin)

    assert schema == {}
    assert "Failed to parse SDK plugin config schema" in caplog.text
    assert str(schema_path) in caplog.text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_config_route_get_plugin_config_supports_sdk_bridge() -> None:
    sdk_bridge = _FakeSdkBridge()
    route, _, _ = _build_config_route(sdk_bridge=sdk_bridge)

    result = await route._get_plugin_config("sdk-demo")

    assert result["config"] == {"count": 1}
    assert result["metadata"] == {
        "sdk-demo": {
            "description": "sdk-demo 配置",
            "type": "object",
            "items": sdk_bridge.schemas["sdk-demo"],
        }
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_post_plugin_configs_saves_and_reloads_sdk_plugin() -> None:
    sdk_bridge = _FakeSdkBridge()
    route, app, plugin_manager = _build_config_route(sdk_bridge=sdk_bridge)

    async with app.test_request_context(
        "/api/config/plugin/update?plugin_name=sdk-demo",
        method="POST",
        json={"count": "2"},
    ):
        response = await route.post_plugin_configs()

    assert response["status"] == "ok"
    assert sdk_bridge.saved == [("sdk-demo", {"count": 2})]
    assert sdk_bridge.reloaded == ["sdk-demo"]
    assert plugin_manager.reloaded == []
