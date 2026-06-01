from astrbot.dashboard.routes.config import (
    _provider_config_enabled,
    _provider_config_selectable,
)


def test_provider_config_enabled_excludes_only_explicitly_disabled_provider():
    assert _provider_config_enabled({"id": "enabled-provider", "enable": True})
    assert _provider_config_enabled({"id": "legacy-provider-without-enable"})
    assert not _provider_config_enabled({"id": "disabled-provider", "enable": False})


def test_provider_config_selectable_requires_loaded_non_agent_provider():
    inst_map = {"loaded-provider": object()}

    assert _provider_config_selectable(
        {"id": "loaded-provider", "enable": True},
        ["chat_completion"],
        inst_map,
    )
    assert not _provider_config_selectable(
        {"enable": True},
        ["chat_completion"],
        inst_map,
    )
    assert not _provider_config_selectable(
        {"id": 123, "enable": True},
        ["chat_completion"],
        inst_map,
    )
    assert not _provider_config_selectable(
        {"id": "unloaded-provider", "enable": True},
        ["chat_completion"],
        inst_map,
    )
    assert not _provider_config_selectable(
        {"id": "disabled-provider", "enable": False},
        ["chat_completion"],
        inst_map,
    )


def test_provider_config_selectable_keeps_agent_runner_configs():
    assert _provider_config_selectable(
        {"id": "agent-runner", "enable": True, "provider_type": "agent_runner"},
        ["agent_runner"],
        {},
    )


def test_provider_config_selectable_does_not_bypass_loaded_check_for_mixed_types():
    assert not _provider_config_selectable(
        {"id": "unloaded-provider", "enable": True, "provider_type": "chat_completion"},
        ["agent_runner", "chat_completion"],
        {},
    )
