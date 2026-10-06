from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from astrbot.core.star.sdk_bridge import SDKPluginBridge
from astrbot.core.star.sdk_bridge.detect import is_isolated_legacy_dir
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import star_handlers_registry
from tests.unit.test_sdk_bridge import FakeCoreEvent, FakeKVStore


async def _empty_snapshot(_context):
    """Stub out the legacy host-state snapshot for MagicMock contexts."""
    return {}


def write_isolated_legacy_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "legacy_bridge_hello",
                "desc": "isolated legacy bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {"isolated": True},
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(
        """
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class LegacyBridgePlugin(Star):
    @filter.command("lhello")
    async def lhello(self, event: AstrMessageEvent):
        yield event.plain_result(f"lhello {event.get_sender_name()}")
""",
        "utf-8",
    )


def test_detect_isolated_legacy_dir(tmp_path: Path) -> None:
    plugin_root = tmp_path / "legacy_optin"
    write_isolated_legacy_plugin(plugin_root)
    assert is_isolated_legacy_dir(plugin_root)

    normal = tmp_path / "legacy_normal"
    normal.mkdir()
    (normal / "metadata.yaml").write_text("name: normal\n", "utf-8")
    assert not is_isolated_legacy_dir(normal)


def test_load_legacy_plugin_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bridge loads _conf_schema.json defaults plus the saved values."""
    import json

    from astrbot.core.star.sdk_bridge.bridge import _load_legacy_plugin_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(
        "astrbot.core.utils.astrbot_path.get_astrbot_config_path",
        lambda: str(config_dir),
    )
    # AstrBotConfig resolves the path at import time in some call sites, so
    # patch the symbol actually imported inside bridge helper as well.
    plugin_root = tmp_path / "conf_plugin"
    plugin_root.mkdir()
    (plugin_root / "_conf_schema.json").write_text(
        json.dumps(
            {
                "greeting": {
                    "description": "greeting text",
                    "type": "string",
                    "default": "hello",
                },
                "level": {
                    "description": "level",
                    "type": "int",
                    "default": 1,
                },
            },
        ),
        "utf-8",
    )
    (config_dir / "conf_plugin_config.json").write_text(
        json.dumps({"level": 5}),
        "utf-8",
    )

    config = _load_legacy_plugin_config(plugin_root, "conf_plugin")
    assert config["greeting"] == "hello"
    assert config["level"] == 5

    no_schema = tmp_path / "plain_plugin"
    no_schema.mkdir()
    assert _load_legacy_plugin_config(no_schema, "plain_plugin") is None


@pytest.mark.asyncio
async def test_bridge_registers_command_group_usage_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy command groups register as CommandGroupFilter anchors."""
    from astrbot.core.star.filter.command import CommandFilter
    from astrbot.core.star.filter.command_group import CommandGroupFilter

    plugin_root = tmp_path / "legacy_group"
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "legacy_group",
                "desc": "command group bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {"isolated": True},
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(
        """
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class LegacyGroupPlugin(Star):
    @filter.command_group("grp")
    def grp(self):
        # group anchor
        pass

    @grp.command("sub")
    async def sub(self, event: AstrMessageEvent, name: str = None):
        yield event.plain_result(f"sub={name}")
""",
        "utf-8",
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge.build_legacy_snapshot",
        _empty_snapshot,
    )
    context = MagicMock()
    bridge = SDKPluginBridge(plugin_root, context, legacy=True)
    group_full_name = f"sdk_bridge.{plugin_root.name}_grp"
    sub_full_name = f"sdk_bridge.{plugin_root.name}_sub"
    try:
        await bridge.start()
        group_handler = star_handlers_registry.star_handlers_map[group_full_name]
        sub_handler = star_handlers_registry.star_handlers_map[sub_full_name]

        group_filter = group_handler.event_filters[0]
        assert isinstance(group_filter, CommandGroupFilter)
        sub_filter = sub_handler.event_filters[0]
        assert isinstance(sub_filter, CommandFilter)
        # The sub-command is linked for the usage tree rendering.
        assert sub_filter in group_filter.sub_command_filters

        # A bare group-name message raises the usage-tree reply, exactly
        # like the in-process CommandGroupFilter.
        with pytest.raises(ValueError, match="参数不足"):
            group_filter.filter(FakeCoreEvent("grp"), None)
        try:
            group_filter.filter(FakeCoreEvent("grp"), None)
        except ValueError as exc:
            assert "sub" in str(exc)

        # The group anchor does not swallow the sub-command message.
        event = FakeCoreEvent("grp sub alice")
        assert not group_filter.equals(event.message_str)
        assert sub_filter.filter(event, None)
        # Host-side param parsing stays empty for legacy handlers; the
        # Runner re-parses arguments authoritatively at invoke time.
        assert event.get_extra("parsed_params") == {}
    finally:
        await bridge.stop()

    assert group_full_name not in star_handlers_registry.star_handlers_map


@pytest.mark.asyncio
async def test_bridge_loads_legacy_plugin_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "legacy_bridge_e2e"
    write_isolated_legacy_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge.build_legacy_snapshot",
        _empty_snapshot,
    )
    context = MagicMock()
    bridge = SDKPluginBridge(plugin_root, context, legacy=True)
    full_name = f"sdk_bridge.{plugin_root.name}_lhello"
    try:
        await bridge.start()
        handler = star_handlers_registry.star_handlers_map[full_name]
        assert f"sdk_bridge.{plugin_root.name}" in star_map

        event = FakeCoreEvent("lhello")
        assert handler.event_filters[0].filter(event, None)
        replies = []
        async for _ in handler.handler(event):
            if event.get_result():
                replies.append(event.get_result().chain[0].text)
            event.clear_result()
        assert replies == ["lhello Moon"]
    finally:
        await bridge.stop()

    assert full_name not in star_handlers_registry.star_handlers_map
