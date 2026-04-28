"""AstrBot CLI entry point"""

import os
import platform
import sys
from pathlib import Path

import click
from click.shell_completion import get_completion_class

from . import __version__
from .commands import conf, init, plug, run, uninstall
from .i18n import t


def print_version_detail() -> None:
    """Print detailed version info (same for --version and version command)"""
    from astrbot.core.utils.astrbot_path import astrbot_paths

    click.echo(f"AstrBot:         {__version__}")
    click.echo(f"Python:          {sys.version.split()[0]}")
    click.echo(f"System:          {platform.system()} {platform.release()}")
    click.echo(f"Machine:         {platform.machine()}")

    git_root = Path(astrbot_paths.root) / ".git"
    if git_root.exists():
        import subprocess

        try:
            git_hash = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(astrbot_paths.root),
                text=True,
            ).strip()
            git_branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(astrbot_paths.root),
                text=True,
            ).strip()
            click.echo(f"Git Branch:      {git_branch}")
            click.echo(f"Git Commit:      {git_hash}")
        except Exception:
            pass

    click.echo(f"AstrBot Root:    {astrbot_paths.root}")
    click.echo(f"Platform:        {platform.platform()}")


def version_callback(ctx: click.Context, param: click.Parameter, value: bool) -> bool:
    """Callback for --version to show detailed version and exit."""
    if not value:
        return value
    print_version_detail()
    ctx.exit()
    return value


@click.group()
@click.option(
    "--version",
    "-v",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=lambda ctx, param, value: value and (print_version_detail(), ctx.exit()),
)
def cli() -> None:
    """AstrBot
    Agentic IM Chatbot infrastructure that integrates lots of IM platforms, LLMs, plugins and AI feature, and can be your openclaw alternative. ✨
    """


@click.command()
@click.argument("command_name", required=False, type=str)
@click.option(
    "--all",
    "-a",
    is_flag=True,
    help="Show help for all commands recursively.",
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
        command = cli.get_command(ctx, command_name)
        if command:
            parent = ctx.parent or ctx
            cmd_ctx = click.Context(command, info_name=command.name, parent=parent)
            click.echo(command.get_help(cmd_ctx))
        else:
            click.echo(t("cli_unknown_command", command=command_name))
            sys.exit(1)
    else:
        click.echo(cli.get_help(ctx))


cli.add_command(init)
cli.add_command(run)
cli.add_command(help)
cli.add_command(plug)
cli.add_command(conf)
cli.add_command(uninstall)


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
        cli,
        ctx_args={},
        prog_name="astrbot",
        complete_var="_ASTRBOT_COMPLETE",
    )
    click.echo(comp.source())


cli.add_command(completion)


@click.command(name="version")
def version_cmd() -> None:
    """Display detailed version information"""
    print_version_detail()


cli.add_command(version_cmd)


if __name__ == "__main__":
    cli()
