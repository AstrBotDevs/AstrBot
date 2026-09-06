from __future__ import annotations

from astrbot.builtin_stars.builtin_commands.commands.plugin import PluginCommands


def test_plugin_commands_imported():
    assert PluginCommands is not None


def test_plugin_commands_class():
    assert issubclass(PluginCommands, object)
    assert hasattr(PluginCommands, "plugin_ls")
    assert hasattr(PluginCommands, "plugin_off")
    assert hasattr(PluginCommands, "plugin_on")
    assert hasattr(PluginCommands, "plugin_get")
    assert hasattr(PluginCommands, "plugin_help")
