"""
AstrBot CLI入口
"""

import click
import sys
from astrbot.cli import __version__


logo_tmpl = r"""
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|
"""


@click.group()
@click.version_option(__version__, prog_name="AstrBot")
def cli() -> None:
    """
    AstrBot CLI \b\n
    @github: https://github.com/AstrBotDevs/AstrBot \b\n
    """
    click.echo(logo_tmpl)
    click.echo("Welcome to AstrBot CLI!")
    click.echo(f"AstrBot CLI version: {__version__}")

# region 基本命令
@cli.command()
@click.argument("command_name", required=False, type=str)
def help(command_name: str | None) -> None:
    """Astrbot CLI helper
    usage: astrbot help [command_name]
    useful commands:
    init: Initialize the Astrbot \n
    run: Run the Astrbot \n 
    plug: Plug in a module to the Astrbot \n
    @github: https://github.com/AstrBotDevs/AstrBot
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

# endregion 基本命令

from astrbot.cli.commands import init, run, plug
cli.add_command(init)
cli.add_command(run)
cli.add_command(plug)


if __name__ == "__main__":
    cli()


