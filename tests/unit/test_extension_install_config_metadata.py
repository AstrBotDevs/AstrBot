from __future__ import annotations

from astrbot.core.config.default import CONFIG_METADATA_3


def test_plugin_group_includes_extension_install_card() -> None:
    plugin_group = CONFIG_METADATA_3["plugin_group"]["metadata"]
    assert "extension_install" in plugin_group

    extension_install = plugin_group["extension_install"]
    assert extension_install["description"] == "扩展安装"
    assert extension_install["type"] == "object"

    items = extension_install["items"]
    assert "provider_settings.extension_install.enable" in items
    assert "provider_settings.extension_install.allowlist" in items
    assert "provider_settings.extension_install.blocklist" in items


def test_extension_install_fields_are_hidden_when_disabled() -> None:
    items = CONFIG_METADATA_3["plugin_group"]["metadata"]["extension_install"]["items"]

    assert "condition" not in items["provider_settings.extension_install.enable"]
    assert items["provider_settings.extension_install.default_mode"]["condition"] == {
        "provider_settings.extension_install.enable": True
    }
    assert items["provider_settings.extension_install.allowlist"]["condition"] == {
        "provider_settings.extension_install.enable": True
    }
    assert items["provider_settings.extension_install.blocklist"]["condition"] == {
        "provider_settings.extension_install.enable": True
    }
