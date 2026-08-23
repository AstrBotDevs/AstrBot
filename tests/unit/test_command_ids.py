from astrbot.core.star.command_ids import (
    legacy_alter_cmd_keys,
    take_alter_cmd_entry,
)


def test_legacy_alter_cmd_keys_include_current_and_fossil_names():
    assert legacy_alter_cmd_keys("builtin_commands:plugin.list", "plugin_list") == (
        "plugin_list",
        "plugin_ls",
    )
    assert legacy_alter_cmd_keys("builtin_commands:admin.grant", "admin_grant") == (
        "admin_grant",
        "op",
    )
    assert "command_id" not in legacy_alter_cmd_keys("builtin_commands:plugin.list")
    assert "plugin_ls" in legacy_alter_cmd_keys("builtin_commands:plugin.list")


def test_take_alter_cmd_entry_migrates_fossil_handler_name():
    plugin_cfg = {
        "plugin_ls": {"permission_action": "extension.read"},
        "op": {"permission_action": "identity.manage"},
    }

    claimed = take_alter_cmd_entry(
        plugin_cfg,
        "builtin_commands:plugin.list",
        "plugin_list",
    )

    assert claimed == {"permission_action": "extension.read"}
    assert plugin_cfg["builtin_commands:plugin.list"] == claimed
    assert "plugin_ls" not in plugin_cfg
    assert "plugin_list" not in plugin_cfg
    assert plugin_cfg["op"] == {"permission_action": "identity.manage"}


def test_take_alter_cmd_entry_prefers_command_id_and_drops_fossils():
    plugin_cfg = {
        "builtin_commands:plugin.list": {"permission_action": "extension.manage"},
        "plugin_ls": {"permission_action": "extension.read"},
        "plugin_list": {"permission_action": "extension.read"},
    }

    claimed = take_alter_cmd_entry(
        plugin_cfg,
        "builtin_commands:plugin.list",
        "plugin_list",
    )

    assert claimed == {"permission_action": "extension.manage"}
    assert "plugin_ls" not in plugin_cfg
    assert "plugin_list" not in plugin_cfg


def test_take_alter_cmd_entry_migrates_current_handler_name():
    plugin_cfg = {"greet": {"permission_action": "session.manage"}}

    claimed = take_alter_cmd_entry(plugin_cfg, "demo:hello", "greet")

    assert claimed == {"permission_action": "session.manage"}
    assert plugin_cfg == {"demo:hello": claimed}


def test_take_alter_cmd_entry_returns_none_without_creating_empty_row():
    plugin_cfg = {"unrelated": {"permission_action": "x.y"}}

    assert take_alter_cmd_entry(plugin_cfg, "demo:hello", "greet") is None
    assert plugin_cfg == {"unrelated": {"permission_action": "x.y"}}
