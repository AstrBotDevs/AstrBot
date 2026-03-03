"""AstrBot CLI entry point"""
from astrbot.core.lang import t
import sys

import click

from . import __version__
from .commands import conf, init, plug, run

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
    """The AstrBot CLI"""
    click.echo(t("msg-fe494da6", logo_tmpl=logo_tmpl))
    click.echo(t("msg-c8b2ff67"))
    click.echo(t("msg-d79e1ff9", __version__=__version__))


@click.command()
@click.argument("command_name", required=False, type=str)
def help(command_name: str | None) -> None:
    """Display help information for commands

    If COMMAND_NAME is provided, display detailed help for that command.
    Otherwise, display general help information.
    """
    ctx = click.get_current_context()
    if command_name:
        # Find the specified command
        command = cli.get_command(ctx, command_name)
        if command:
            # Display help for the specific command
            click.echo(t("msg-78b9c276", res=command.get_help(ctx)))
        else:
            click.echo(t("msg-14dd710d", command_name=command_name))
            sys.exit(1)
    else:
        # Display general help information
        click.echo(t("msg-78b9c276", res=cli.get_help(ctx)))


cli.add_command(init)
cli.add_command(run)
cli.add_command(help)
cli.add_command(plug)
cli.add_command(conf)

if __name__ == "__main__":
    cli()
