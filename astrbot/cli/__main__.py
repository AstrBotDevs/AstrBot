"""AstrBot CLI入口"""

import sys
from importlib.metadata import version

import click

from astrbot.base import LOGO

from .commands import conf, init, plug, run

__version__ = version("astrbot")
""" 注意,此版本号可能包含.dev+hash后缀,仅用于开发版本识别.

请勿直接使用本版本号来下载dashboard.
"""


@click.group()
@click.version_option(__version__, prog_name="AstrBot")
def cli() -> None:
    """The AstrBot CLI"""
    click.echo(LOGO)
    click.echo("Welcome to AstrBot CLI!")
    click.echo(f"AstrBot CLI version: {__version__}")


@click.command()
@click.argument("command_name", required=False, type=str)
def help(command_name: str | None) -> None:
    """显示命令的帮助信息

    如果提供了 COMMAND_NAME，则显示该命令的详细帮助信息。
    否则，显示通用帮助信息。
    """
    ctx = click.get_current_context()
    if command_name:
        # 查找指定命令
        command = cli.get_command(ctx, command_name)
        if command:
            # 显示特定命令的帮助信息
            click.echo(command.get_help(ctx))
        else:
            click.echo(f"Unknown command: {command_name}")
            sys.exit(1)
    else:
        # 显示通用帮助信息
        click.echo(cli.get_help(ctx))


cli.add_command(init)
cli.add_command(run)
cli.add_command(help)
cli.add_command(plug)
cli.add_command(conf)

if __name__ == "__main__":
    cli()
