from astrbot.core.star.command_ids import take_alter_cmd_entry


def test_take_alter_cmd_entry_reads_command_id_only():
    plugin_cfg = {
        "builtin_commands:plugin.list": {"permission_action": "extension.manage"},
        "plugin_ls": {"permission_action": "extension.read"},
        "plugin_list": {"permission_action": "extension.read"},
    }

    claimed = take_alter_cmd_entry(plugin_cfg, "builtin_commands:plugin.list")

    assert claimed == {"permission_action": "extension.manage"}
    assert plugin_cfg["plugin_ls"] == {"permission_action": "extension.read"}
    assert plugin_cfg["plugin_list"] == {"permission_action": "extension.read"}


def test_take_alter_cmd_entry_ignores_handler_name_keys():
    plugin_cfg = {"greet": {"permission_action": "session.manage"}}

    assert take_alter_cmd_entry(plugin_cfg, "demo:hello") is None
    assert plugin_cfg == {"greet": {"permission_action": "session.manage"}}


def test_take_alter_cmd_entry_returns_none_without_mutating():
    plugin_cfg = {"unrelated": {"permission_action": "x.y"}}

    assert take_alter_cmd_entry(plugin_cfg, "demo:hello") is None
    assert plugin_cfg == {"unrelated": {"permission_action": "x.y"}}
