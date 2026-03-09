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
    assert "provider_settings.extension_install.confirm_keyword" in items
    assert "provider_settings.extension_install.deny_keyword" in items
    assert "provider_settings.extension_install.confirm_keywords" not in items
    assert (
        "provider_settings.extension_install.confirmation_required_non_allowlist"
        not in items
    )


def test_extension_install_fields_are_hidden_when_disabled() -> None:
    items = CONFIG_METADATA_3["plugin_group"]["metadata"]["extension_install"]["items"]

    assert "condition" not in items["provider_settings.extension_install.enable"]
    assert items["provider_settings.extension_install.default_mode"]["condition"] == {
        "provider_settings.extension_install.enable": True
    }
    assert items["provider_settings.extension_install.allowlist"]["condition"] == {
        "provider_settings.extension_install.enable": True,
        "provider_settings.extension_install.default_mode": "secure",
    }
    assert items["provider_settings.extension_install.blocklist"]["condition"] == {
        "provider_settings.extension_install.enable": True
    }


def test_extension_install_rule_editor_only_exposes_author() -> None:
    items = CONFIG_METADATA_3["plugin_group"]["metadata"]["extension_install"]["items"]
    allowlist_rule = items["provider_settings.extension_install.allowlist"]["templates"][
        "rule"
    ]["items"]
    blocklist_rule = items["provider_settings.extension_install.blocklist"]["templates"][
        "rule"
    ]["items"]

    assert allowlist_rule["kind"]["invisible"] is True
    assert allowlist_rule["kind"]["default"] == "plugin"
    assert "author" in allowlist_rule
    assert "provider" not in allowlist_rule
    assert "identifier" not in allowlist_rule

    assert blocklist_rule["kind"]["invisible"] is True
    assert blocklist_rule["kind"]["default"] == "plugin"
    assert "author" in blocklist_rule
    assert "provider" not in blocklist_rule
    assert "identifier" not in blocklist_rule
