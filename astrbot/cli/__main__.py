"""AstrBot CLI entry point"""

import os
import sys

import click
from click.shell_completion import get_completion_class

from . import __version__
from .commands import bk, conf, init, plug, run, tui, uninstall
from .i18n import t

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
    """Astrbot
    Agentic IM Chatbot infrastructure that integrates lots of IM platforms, LLMs, plugins and AI feature, and can be your openclaw alternative. ✨
    """
    click.echo(logo_tmpl)
    click.echo(t("cli_welcome"))
    click.echo(t("cli_version", version=__version__))


@click.command()
@click.argument("command_name", required=False, type=str)
@click.option(
    "--all", "-a", is_flag=True, help="Show help for all commands recursively."
)
def help(command_name: str | None, all: bool) -> None:
    """Display help information for commands

    If COMMAND_NAME is provided, display detailed help for that command.
    Otherwise, display general help information.
    """
    ctx = click.get_current_context()

    if all:

        def print_recursive_help(command, parent_ctx):
            name = command.name
            if parent_ctx is None:
                name = "astrbot"

            cmd_ctx = click.Context(command, info_name=name, parent=parent_ctx)
            click.echo(command.get_help(cmd_ctx))
            click.echo("\n" + "-" * 50 + "\n")

            if isinstance(command, click.Group):
                for subcommand in command.commands.values():
                    print_recursive_help(subcommand, cmd_ctx)

        print_recursive_help(cli, None)
        return

    if command_name:
        # Find the specified command
        command = cli.get_command(ctx, command_name)
        if command:
            # Display help for the specific command
            parent = ctx.parent if ctx.parent else ctx
            cmd_ctx = click.Context(command, info_name=command.name, parent=parent)
            click.echo(command.get_help(cmd_ctx))
        else:
            click.echo(t("cli_unknown_command", command=command_name))
            sys.exit(1)
    else:
        # Display general help information
        click.echo(cli.get_help(ctx))


cli.add_command(init)
cli.add_command(run)
cli.add_command(help)
cli.add_command(plug)
cli.add_command(conf)
cli.add_command(uninstall)
cli.add_command(bk)
cli.add_command(tui)


@click.command()
@click.argument("shell", required=False, type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell: str | None) -> None:
    """Generate shell completion script"""
    if shell is None:
        shell_path = os.environ.get("SHELL", "")
        if "zsh" in shell_path:
            shell = "zsh"
        elif "bash" in shell_path:
            shell = "bash"
        elif "fish" in shell_path:
            shell = "fish"
        else:
            click.echo(
                "Could not detect shell. Please specify one of: bash, zsh, fish",
                err=True,
            )
            sys.exit(1)

    comp_cls = get_completion_class(shell)
    if comp_cls is None:
        click.echo(f"No completion support for shell: {shell}", err=True)
        sys.exit(1)
    comp = comp_cls(
        cli, ctx_args={}, prog_name="astrbot", complete_var="_ASTRBOT_COMPLETE"
    )
    click.echo(comp.source())


cli.add_command(completion)

if __name__ == "__main__":
    cli()
