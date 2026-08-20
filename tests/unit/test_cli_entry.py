import click
from click.testing import CliRunner

from astrbot.cli.__main__ import LazyCommandGroup, cli


def test_cli_help_lists_lazy_commands():
    runner = CliRunner()
    result = runner.invoke(cli, ["help"])
    assert result.exit_code == 0
    assert "AstrBot CLI" in result.output

    missing = runner.invoke(cli, ["help", "not-a-command"])
    assert missing.exit_code == 1
    assert "Unknown command" in missing.output


def test_lazy_command_group_resolves_known_and_unknown_commands():
    group = LazyCommandGroup()
    ctx = click.Context(cli)
    assert "run" in group.list_commands(ctx)
    assert group.get_command(ctx, "run") is not None
    assert group.get_command(ctx, "missing") is None
