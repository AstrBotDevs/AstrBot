"""Tests for dependency graph scheduling, isolation, and non-transitive cross-plugin services."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from astrbot_sdk.runtime.metadata import (
    CapabilityDeclarations,
    PluginAPIFamily,
    PluginMetadata,
    RuntimeMetadata,
)

import astrbot.core.message.components as core_comp
from astrbot.core.platform.message_type import MessageType as CoreMessageType
from astrbot.core.star.sdk_bridge.bridge import SDKPluginManager
from astrbot.core.star.sdk_bridge.dependencies import build_dependency_plan
from astrbot.core.star.star_handler import star_handlers_registry


class FakeCoreEvent:
    """Minimal event double for testing cross-plugin command execution."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.unified_msg_origin = "webchat:FriendMessage:user-1"
        self.platform_meta = SimpleNamespace(name="webchat", id="webchat")
        self.session_id = "user-1"
        self._extras: dict = {}
        self._result = None
        self._stopped = False
        self._has_send_oper = False
        self.role = "member"
        self.is_wake = True
        self.is_at_or_wake_command = True
        self.plugins_name = None
        self.message_str = text
        self.trace = MagicMock()
        self.message_obj = SimpleNamespace(
            message_id="m-1",
            self_id="bot-1",
            session_id="user-1",
            group_id="",
            sender=SimpleNamespace(user_id="user-1", nickname="Moon"),
            message=[core_comp.Plain(text)],
            timestamp=1700000000,
            raw_message=None,
        )

    def get_platform_name(self):
        return "webchat"

    def get_platform_id(self):
        return "webchat"

    def get_message_type(self):
        return CoreMessageType(self.unified_msg_origin.split(":", 2)[1])

    def get_messages(self):
        return [core_comp.Plain(self._text)]

    def get_message_str(self):
        return self._text

    def get_sender_id(self):
        return "user-1"

    def get_sender_name(self):
        return "Moon"

    def set_extra(self, key, value):
        self._extras[key] = value

    def get_extra(self, key, default=None):
        return self._extras.get(key, default)

    def set_result(self, result):
        self._result = result

    def get_result(self):
        return self._result

    def clear_result(self):
        self._result = None

    def stop_event(self):
        self._stopped = True

    def is_stopped(self):
        return self._stopped


def _meta(
    plugin_id: str,
    version: str,
    deps: dict[str, str] | None = None,
) -> PluginMetadata:
    author, _, name = plugin_id.partition("/")
    return PluginMetadata(
        schema_version=2,
        name=name or plugin_id,
        desc="",
        author=author or "AstrBot",
        version=version,
        runtime=RuntimeMetadata(
            api=PluginAPIFamily.SDK,
            entrypoint="main:Plugin",
            module="main",
            plugin_class="Plugin",
            sdk_version=">=0.1,<0.2",
        ),
        capabilities=CapabilityDeclarations(),
        dependencies=deps or {},
    )


def test_dependency_plan_topological_order_and_blocking() -> None:
    """DependencyPlan orders dependencies cleanly and isolates missing/incompatible/cyclic nodes."""
    plan = build_dependency_plan(
        {
            "plugin_a": _meta("org/a", "1.0.0", {"org/b": ">=1.0"}),
            "plugin_b": _meta("org/b", "1.2.0", {"org/c": ">=1.0,<2.0"}),
            "plugin_c": _meta("org/c", "1.5.0"),
            "plugin_mismatch": _meta("org/m", "1.0.0", {"org/c": ">=2.0"}),
            "plugin_missing": _meta("org/miss", "1.0.0", {"org/unknown": ">=1.0"}),
            "cycle_1": _meta("org/cyc1", "1.0.0", {"org/cyc2": ">=1.0"}),
            "cycle_2": _meta("org/cyc2", "1.0.0", {"org/cyc1": ">=1.0"}),
        }
    )

    assert plan.load_order == ("plugin_c", "plugin_b", "plugin_a")
    assert plan.unload_order == ("plugin_a", "plugin_b", "plugin_c")
    assert plan.dependents_of("plugin_c") == ("plugin_a", "plugin_b")
    assert set(plan.blocked.keys()) == {
        "plugin_mismatch",
        "plugin_missing",
        "cycle_1",
        "cycle_2",
    }
    assert all(b.code == "DEPENDENCY_BLOCKED" for b in plan.blocked.values())


def _write_plugin(
    root: Path,
    *,
    author: str,
    name: str,
    version: str,
    deps: dict[str, str],
    source: str,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "name": name,
                "desc": "dependency/service test",
                "author": author,
                "version": version,
                "dependencies": deps,
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:TestPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {"required": []},
            }
        ),
        encoding="utf-8",
    )
    (root / "main.py").write_text(source, encoding="utf-8")


@pytest.mark.asyncio
async def test_manager_dependency_isolation_and_non_transitive_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manager isolates blocked plugins, preserves direct-service privileges, and blocks transitive service calls."""
    cfg_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    plugins_dir = tmp_path / "plugins"
    cfg_dir.mkdir()
    data_dir.mkdir()
    plugins_dir.mkdir()

    monkeypatch.setattr(
        "astrbot.core.utils.astrbot_path.get_astrbot_config_path",
        lambda: str(cfg_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.astrbot_path.get_astrbot_data_path",
        lambda: str(data_dir),
    )

    _write_plugin(
        plugins_dir / "plugin_a",
        author="org",
        name="a",
        version="1.0.0",
        deps={"org/b": ">=1.0"},
        source="""
from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.errors import CapabilityDenied


class TestPlugin(Plugin):
    @on.command("test_calls")
    async def test_calls(self, event: MessageEvent):
        via_b = await self.ctx.plugins.call_service("org/b", "proxy", {"x": 7})
        try:
            await self.ctx.plugins.call_service("org/c", "compute", {"x": 7})
            direct_c = "UNEXPECTED_OK"
        except CapabilityDenied:
            direct_c = "DENIED"
        yield event.reply(f"b={via_b['res']},c={direct_c}")
""".strip(),
    )
    _write_plugin(
        plugins_dir / "plugin_b",
        author="org",
        name="b",
        version="1.1.0",
        deps={"org/c": ">=1.0"},
        source="""
from astrbot_sdk import Plugin, on


class TestPlugin(Plugin):
    @on.service("proxy")
    async def proxy(self, payload: dict[str, Any] | None = None):
        x = (payload or {}).get("x", 0)
        c_res = await self.ctx.plugins.call_service("org/c", "ping_direct", {"v": x})
        return {"res": c_res}
""".replace("dict[str, Any] | None", "dict"),
    )
    _write_plugin(
        plugins_dir / "plugin_c",
        author="org",
        name="c",
        version="1.2.0",
        deps={},
        source="""
from astrbot_sdk import DirectContext, Plugin, on


class TestPlugin(Plugin):
    @on.direct_service("ping_direct")
    async def ping_direct(self, payload: dict, ctx: DirectContext):
        assert isinstance(ctx, DirectContext)
        assert not hasattr(ctx, "storage")
        assert not hasattr(ctx, "messages")
        return {"ok": True, "v": payload.get("v")}

    @on.service("compute")
    async def compute(self, payload: dict):
        return {"computed": payload.get("v", 0) * 2}
""".strip(),
    )
    _write_plugin(
        plugins_dir / "plugin_broken",
        author="org",
        name="broken",
        version="1.0.0",
        deps={"org/missing": ">=1.0"},
        source="""
from astrbot_sdk import Plugin


class TestPlugin(Plugin):
    pass
""".strip(),
    )

    manager = SDKPluginManager(MagicMock(), plugins_dir)
    try:
        loaded = await manager.load_all()
        assert loaded == ["plugin_c", "plugin_b", "plugin_a"]
        assert "plugin_broken" in manager.blocked_plugins
        assert manager.blocked_plugins["plugin_broken"].code == "DEPENDENCY_BLOCKED"

        handler = star_handlers_registry.star_handlers_map[
            "sdk_bridge.plugin_a_test_calls"
        ]
        ev = FakeCoreEvent("test_calls")
        outputs = []
        async for _ in handler.handler(ev):
            if ev.get_result():
                outputs.append(ev.get_result().chain[0].text)
            ev.clear_result()
        assert outputs == ["b={'ok': True, 'v': 7},c=DENIED"]
    finally:
        await manager.stop_all()
