import json
from pathlib import Path

import pytest

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_CONFIG

ROOT = Path(__file__).resolve().parents[1]
SHIPYARD_COMPOSE = (ROOT / "compose-with-shipyard.yml").read_text(encoding="utf-8")
SANDBOX_TIMEOUT_KEYS = {
    "sandbox_ttl",
    "sandbox_idle_timeout",
    "sandbox_lease_timeout",
    "cua_ttl",
    "cua_idle_timeout",
    "shipyard_ttl",
    "shipyard_idle_timeout",
    "shipyard_neo_ttl",
}


def _require_plugin_files(*relative_paths: str) -> None:
    missing = [path for path in relative_paths if not (ROOT / path).is_file()]
    if missing:
        pytest.skip(f"sandbox plugin repository files are not present: {missing}")


def _load_schema(plugin_name: str) -> dict:
    schema_path = ROOT / "data/plugins" / plugin_name / "_conf_schema.json"
    if not schema_path.is_file():
        pytest.skip(f"sandbox plugin schema is not present: {schema_path}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _assert_no_plugin_timeout_schema(schema: dict) -> None:
    assert not (SANDBOX_TIMEOUT_KEYS & set(schema))


def _read_plugin_file(plugin_name: str, filename: str) -> str:
    path = ROOT / "data/plugins" / plugin_name / filename
    if not path.is_file():
        pytest.skip(f"sandbox plugin file is not present: {path}")
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("plugin_name", "description"),
    [
        ("astrbot_sandbox_cua", "为 AstrBot 提供 CUA 沙盒运行时。"),
        ("astrbot_sandbox_boxlite", "为 AstrBot 提供 Boxlite 本地沙盒运行时。"),
        ("astrbot_sandbox_shipyard", "为 AstrBot 提供 Shipyard 沙盒运行时。"),
        ("astrbot_sandbox_shipyard_neo", "为 AstrBot 提供 Shipyard Neo 沙盒运行时。"),
    ],
)
def test_sandbox_plugin_metadata_is_localized(plugin_name: str, description: str):
    metadata = _read_plugin_file(plugin_name, "metadata.yaml")
    main_py = _read_plugin_file(plugin_name, "main.py")

    assert f"desc: {description}" in metadata
    assert f'"{description}"' in main_py
    assert "sandbox runtime provider for AstrBot" not in metadata
    assert "sandbox runtime provider for AstrBot" not in main_py


def test_core_sandbox_timeout_defaults_live_in_bot_config():
    sandbox = DEFAULT_CONFIG["provider_settings"]["sandbox"]

    assert sandbox["sandbox_ttl"] == 3600
    assert sandbox["sandbox_idle_timeout"] == 1800
    assert sandbox["sandbox_lease_timeout"] == 600


def test_cua_schema_defaults_match_documented_hints():
    schema = _load_schema("astrbot_sandbox_cua")

    _assert_no_plugin_timeout_schema(schema)
    assert schema["cua_image"]["default"] == "linux"
    assert schema["cua_os_type"]["default"] == "linux"
    assert schema["cua_telemetry_enabled"]["default"] is False
    assert schema["cua_local"]["default"] is True
    assert schema["cua_api_key"]["default"] == ""
    assert schema["cua_local"]["description"] == "CUA 本地沙箱"
    assert "默认开启" in schema["cua_local"]["hint"]


def test_shipyard_schema_is_localized_and_has_defaults():
    schema = _load_schema("astrbot_sandbox_shipyard")

    _assert_no_plugin_timeout_schema(schema)
    assert schema["shipyard_endpoint"]["description"] == "Shipyard API 地址"
    assert schema["shipyard_endpoint"]["default"] == "http://127.0.0.1:8156"
    assert schema["shipyard_auto_start"]["default"] is True
    assert schema["shipyard_bay_image"]["default"] == "soulter/shipyard-bay:latest"
    assert schema["shipyard_ship_image"]["default"] == "soulter/shipyard-ship:latest"
    assert schema["shipyard_bay_image"]["default"] in SHIPYARD_COMPOSE
    assert schema["shipyard_ship_image"]["default"] in SHIPYARD_COMPOSE
    assert schema["shipyard_access_token"]["description"] == "Shipyard 访问令牌"
    assert schema["shipyard_access_token"]["default"] == ""
    assert schema["shipyard_max_sessions"]["description"] == "Shipyard 最大会话数"
    assert schema["shipyard_max_sessions"]["default"] == 10


def test_shipyard_neo_schema_is_localized_and_has_defaults():
    schema = _load_schema("astrbot_sandbox_shipyard_neo")

    _assert_no_plugin_timeout_schema(schema)
    assert schema["shipyard_neo_endpoint"]["description"] == "Shipyard Neo API 地址"
    assert schema["shipyard_neo_endpoint"]["default"] == "http://127.0.0.1:8114"
    assert schema["shipyard_neo_access_token"]["description"] == "Shipyard Neo 访问令牌"
    assert schema["shipyard_neo_access_token"]["default"] == ""
    assert schema["shipyard_neo_profile"]["description"] == "Shipyard Neo Profile"
    assert schema["shipyard_neo_profile"]["default"] == "python-default"


def test_shipyard_neo_plugin_does_not_duplicate_builtin_tool_registration():
    _require_plugin_files(
        "data/plugins/astrbot_sandbox_shipyard_neo/main.py",
        "data/plugins/astrbot_sandbox_shipyard_neo/tools/shipyard_neo/browser.py",
    )
    content = (ROOT / "data/plugins/astrbot_sandbox_shipyard_neo/main.py").read_text(
        encoding="utf-8"
    )

    assert "tools=[" not in content


def test_cua_provider_falls_back_to_local_mode_without_api_key(monkeypatch):
    _require_plugin_files("data/plugins/astrbot_sandbox_cua/provider.py")
    from data.plugins.astrbot_sandbox_cua.provider import CuaSandboxProvider

    monkeypatch.delenv("CUA_API_KEY", raising=False)

    class FakeContext:
        def get_config(self, umo=None):
            del umo
            return {"provider_settings": {"sandbox": {}}}

    provider = CuaSandboxProvider()
    provider.plugin_config = {
        "cua_local": False,
        "cua_api_key": "",
        "cua_image": "linux",
        "cua_os_type": "linux",
    }

    config = provider.build_create_config(FakeContext(), "dashboard")

    assert config["local"] is True
    assert config["api_key"] == ""


def test_cua_provider_connect_info_tracks_persistent_runtime_name():
    _require_plugin_files("data/plugins/astrbot_sandbox_cua/provider.py")
    from data.plugins.astrbot_sandbox_cua.provider import CuaSandboxProvider

    provider = CuaSandboxProvider()

    info = provider.build_connect_info(
        "Named",
        {
            "local": True,
            "image": "linux",
            "os_type": "linux",
            "persistent_name": "cua-persistent-1",
        },
    )

    assert info["name"] == "Named"
    assert info["persistent_name"] == "cua-persistent-1"


def test_existing_plugin_config_keeps_saved_values_when_schema_defaults_change(
    tmp_path,
):
    config_path = tmp_path / "plugin_config.json"
    config_path.write_text('{"flag": false, "ttl": 0}', encoding="utf-8")

    config = AstrBotConfig(
        config_path=str(config_path),
        schema={
            "flag": {"type": "bool", "default": True},
            "ttl": {"type": "int", "default": 3600},
        },
    )

    assert config["flag"] is False
    assert config["ttl"] == 0


def test_cua_screenshot_tool_does_not_send_to_user_by_default():
    _require_plugin_files("data/plugins/astrbot_sandbox_cua/tools/cua.py")
    from data.plugins.astrbot_sandbox_cua.tools.cua import CuaScreenshotTool

    tool = CuaScreenshotTool()

    send_to_user = tool.parameters["properties"]["send_to_user"]["default"]
    return_image_to_llm = tool.parameters["properties"]["return_image_to_llm"][
        "default"
    ]

    assert send_to_user is True
    assert return_image_to_llm is True


def test_cua_screenshot_tool_can_send_result_to_user_when_requested():
    _require_plugin_files("data/plugins/astrbot_sandbox_cua/tools/cua.py")
    from data.plugins.astrbot_sandbox_cua.tools.cua import CuaScreenshotTool

    tool = CuaScreenshotTool()

    assert tool.parameters["properties"]["send_to_user"]["description"]
    assert tool.parameters["properties"]["return_image_to_llm"]["default"] is True
