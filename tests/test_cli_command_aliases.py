from click.testing import CliRunner

from astrbot.cli.__main__ import cli


def test_top_level_help_uses_product_command_names():
    result = CliRunner().invoke(cli, ["help"])

    assert result.exit_code == 0
    assert "config" in result.output
    assert "plugin" in result.output
    assert " conf " not in result.output
    assert " plug " not in result.output


def test_legacy_config_and_plugin_aliases_still_work():
    runner = CliRunner()

    config_result = runner.invoke(cli, ["help", "conf"])
    plugin_result = runner.invoke(cli, ["help", "plug"])

    assert config_result.exit_code == 0
    assert "Configuration management commands" in config_result.output
    assert plugin_result.exit_code == 0
    assert "Plugin management" in plugin_result.output
