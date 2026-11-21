"""Tests for typed SDK plugin config validation, live reload, redaction, and 404 gating."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from astrbot_sdk.errors import InvalidConfig

import astrbot.core.message.components as core_comp
from astrbot.core.platform.message_type import MessageType as CoreMessageType
from astrbot.core.star.sdk_bridge.bridge import SDKPluginManager
from astrbot.core.star.sdk_bridge.config_schema import (
    load_plugin_json_schema,
    plugin_has_sensitive_schema,
    redact_write_only_fields,
    to_astrbot_config_schema,
)
from astrbot.dashboard.api.plugins import _ensure_raw_config_files_allowed
from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.services.config_service import (
    ConfigDisplayService,
    ConfigFileService,
)


class FakeKVStore:
    """In-memory plugin KV store test double."""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str, str], object] = {}

    async def put_async(self, scope: str, plugin_id: str, key: str, value: object):
        self.data[(scope, plugin_id, key)] = value

    async def get_async(
        self,
        scope: str,
        plugin_id: str,
        key: str,
        default: object = None,
    ):
        return self.data.get((scope, plugin_id, key), default)

    async def remove_async(self, scope: str, plugin_id: str, key: str):
        self.data.pop((scope, plugin_id, key), None)


class FakeCoreEvent:
    """Minimal event double for driving SDK command stubs."""

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


def test_config_schema_offline_validation_and_redaction(tmp_path: Path) -> None:
    """Schema loader rejects >64 KiB and external $ref while supporting translation and redaction."""
    oversized = tmp_path / "oversized"
    oversized.mkdir()
    (oversized / "config.schema.json").write_bytes(b"{}" + b" " * (65 * 1024))
    with pytest.raises(InvalidConfig, match="64 KiB"):
        load_plugin_json_schema(oversized)
    assert plugin_has_sensitive_schema(oversized) is False

    ext_ref = tmp_path / "ext_ref"
    ext_ref.mkdir()
    (ext_ref / "config.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "token": {"$ref": "https://example.com/secret.json"},
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(InvalidConfig, match="external"):
        load_plugin_json_schema(ext_ref)

    valid_dir = tmp_path / "valid"
    valid_dir.mkdir()
    schema = {
        "type": "object",
        "$defs": {
            "Secret": {
                "type": "string",
                "format": "password",
                "description": "Secret key",
            }
        },
        "properties": {
            "secret": {"$ref": "#/$defs/Secret", "default": ""},
            "limit": {"type": "integer", "default": 5, "description": "Max items"},
        },
    }
    (valid_dir / "config.schema.json").write_text(json.dumps(schema), encoding="utf-8")

    loaded = load_plugin_json_schema(valid_dir)
    assert loaded == schema
    assert plugin_has_sensitive_schema(valid_dir) is True

    translated = to_astrbot_config_schema(schema)
    assert translated["limit"]["type"] == "int"
    assert translated["limit"]["default"] == 5
    assert translated["secret"]["type"] == "string"
    assert "Sensitive" in translated["secret"]["hint"]

    raw_values = {"secret": "top-secret", "limit": 5}
    redacted = redact_write_only_fields(schema, raw_values)
    assert redacted == {"secret": "", "limit": 5}
    assert raw_values["secret"] == "top-secret"


@pytest.mark.asyncio
async def test_config_lifecycle_pre_save_validation_live_configure_and_redaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ConfigService validates offline, checks Worker before saving, applies live without PID restart, and gates raw files."""
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
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )

    plugin_dir = plugins_dir / "cfg_e2e"
    plugin_dir.mkdir()
    (plugin_dir / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "id": "test/cfg_e2e",
                "name": "plugin_cfg_e2e",
                "desc": "Typed config test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:CfgPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {"required": []},
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "config.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "api_key": {
                        "type": "string",
                        "default": "",
                        "writeOnly": True,
                        "description": "API key",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Item limit",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        """
import os
from pydantic import Field
from astrbot_sdk import MessageEvent, Plugin, PluginConfig, lifecycle, on


class CfgModel(PluginConfig):
    api_key: str = Field(default="", json_schema_extra={"writeOnly": True})
    limit: int = Field(default=3, ge=1, le=10)


class CfgPlugin(Plugin[CfgModel]):
    config_model = CfgModel

    @lifecycle.validate_config
    async def check_cfg(self, candidate: CfgModel) -> None:
        if candidate.limit == 8:
            raise ValueError("limit=8 is reserved by policy")

    @lifecycle.config_changed
    async def apply_cfg(self, event) -> None:
        if event.current.limit == 9:
            raise RuntimeError("backend rejected limit=9")

    @on.command("cfg")
    async def show_cfg(self, event: MessageEvent):
        cur = self.ctx.current_config()
        yield event.reply(f"limit={cur.limit},key={cur.api_key},pid={os.getpid()}")
""".strip(),
        encoding="utf-8",
    )

    on_disk_cfg = cfg_dir / "cfg_e2e_config.json"
    on_disk_cfg.write_text(
        json.dumps({"api_key": "initial-secret", "limit": 3}),
        encoding="utf-8",
    )

    context = MagicMock()
    manager = SDKPluginManager(context, plugins_dir)
    pm_stub = SimpleNamespace(
        _sdk_plugin_manager=manager,
        plugin_store_path=plugins_dir,
        reload=AsyncMock(return_value=(True, None)),
    )
    core_lifecycle = SimpleNamespace(astrbot_config={}, plugin_manager=pm_stub)
    display_service = ConfigDisplayService(core_lifecycle)
    file_service = ConfigFileService(core_lifecycle)

    try:
        loaded = await manager.load_all()
        assert loaded == ["cfg_e2e"]
        bridge = manager.bridges["cfg_e2e"]
        initial_pid = bridge.runner_pid
        assert initial_pid is not None and initial_pid > 0

        # Dashboard display masks writeOnly fields without mutating runtime config.
        displayed = display_service.get_plugin_config(bridge.plugin_name)
        assert displayed["config"]["api_key"] == ""
        assert displayed["config"]["limit"] == 3
        assert bridge._plugin_config["api_key"] == "initial-secret"

        # JSON Schema check fails before touching disk.
        with pytest.raises(ValueError, match="格式校验未通过"):
            await file_service.save_plugin_configs(
                {"api_key": "secret2", "limit": 99},
                bridge.plugin_name,
            )
        assert json.loads(on_disk_cfg.read_text(encoding="utf-8-sig"))["limit"] == 3

        # Worker @lifecycle.validate_config rejects before touching disk.
        with pytest.raises(ValueError, match="reserved by policy"):
            await file_service.save_plugin_configs(
                {"api_key": "secret2", "limit": 8},
                bridge.plugin_name,
            )
        assert json.loads(on_disk_cfg.read_text(encoding="utf-8-sig"))["limit"] == 3

        # Valid config saves and hot-updates live Worker without reloading/restarting PID.
        await file_service.save_plugin_configs(
            {"api_key": "secret2", "limit": 5},
            bridge.plugin_name,
        )
        pm_stub.reload.assert_not_awaited()
        assert bridge.runner_pid == initial_pid
        assert json.loads(on_disk_cfg.read_text(encoding="utf-8-sig")) == {
            "api_key": "secret2",
            "limit": 5,
        }

        from astrbot.core.star.star_handler import star_handlers_registry

        handler = star_handlers_registry.star_handlers_map[
            f"sdk_bridge.{plugin_dir.name}_show_cfg"
        ]
        ev = FakeCoreEvent("cfg")
        outputs = []
        async for _ in handler.handler(ev):
            if ev.get_result():
                outputs.append(ev.get_result().chain[0].text)
            ev.clear_result()
        assert outputs == [f"limit=5,key=secret2,pid={initial_pid}"]

        # @lifecycle.config_changed failure rolls back on-disk config to limit=5.
        with pytest.raises(ValueError, match="回滚"):
            await file_service.save_plugin_configs(
                {"api_key": "secret2", "limit": 9},
                bridge.plugin_name,
            )
        assert json.loads(on_disk_cfg.read_text(encoding="utf-8-sig"))["limit"] == 5
        assert bridge.runner_pid == initial_pid

        # Raw config-file routes return HTTP 404 when config.schema.json marks secrets.
        with pytest.raises(ApiError) as exc_info:
            _ensure_raw_config_files_allowed(file_service, bridge.plugin_name)
        assert exc_info.value.status_code == 404
    finally:
        await manager.stop_all()
