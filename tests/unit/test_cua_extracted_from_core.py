import importlib.util

from astrbot.core.config.default import DEFAULT_CONFIG


def test_core_no_longer_ships_concrete_sandbox_runtime_modules():
    assert importlib.util.find_spec("astrbot.core.computer.booters.cua") is None
    assert (
        importlib.util.find_spec("astrbot.core.computer.booters.cua_defaults") is None
    )
    assert importlib.util.find_spec("astrbot.core.tools.computer_tools.cua") is None
    assert importlib.util.find_spec("astrbot.core.computer.booters.shipyard") is None
    assert (
        importlib.util.find_spec("astrbot.core.computer.booters.shipyard_neo") is None
    )
    assert importlib.util.find_spec("astrbot.core.computer.booters.boxlite") is None
    assert importlib.util.find_spec("astrbot.core.computer.booters.bay_manager") is None
    assert (
        importlib.util.find_spec("astrbot.core.computer.booters.shell_background")
        is None
    )
    assert (
        importlib.util.find_spec(
            "astrbot.core.computer.booters.shipyard_search_file_util"
        )
        is None
    )
    assert (
        importlib.util.find_spec("astrbot.core.tools.computer_tools.shipyard_neo")
        is None
    )


def test_core_default_config_does_not_include_runtime_specific_settings():
    sandbox = DEFAULT_CONFIG["provider_settings"]["sandbox"]

    assert sandbox == {"booter": ""}
    assert "cua_image" not in sandbox
    assert "cua_os_type" not in sandbox
    assert "cua_ttl" not in sandbox
    assert "cua_telemetry_enabled" not in sandbox
    assert "cua_local" not in sandbox
    assert "cua_api_key" not in sandbox
    assert "shipyard_endpoint" not in sandbox
    assert "shipyard_neo_endpoint" not in sandbox
    assert "shipyard_neo_profile" not in sandbox


def test_core_sandbox_config_metadata_is_provider_agnostic():
    from astrbot.core.config.default import CONFIG_METADATA_3

    items = CONFIG_METADATA_3["ai_group"]["metadata"]["agent_computer_use"]["items"]
    booter = items["provider_settings.sandbox.booter"]

    assert booter["options"] == []
    assert booter["labels"] == []
    assert not any("shipyard" in key or "cua" in key for key in items)
