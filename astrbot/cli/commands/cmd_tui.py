"""TUI CLI command for AstrBot."""

from __future__ import annotations

import sys

import click


@click.command(name="tui")
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug mode with verbose output.",
)
@click.option(
    "--host",
    default="http://localhost:6185",
    help="AstrBot dashboard host URL.",
)
@click.option(
    "--api-key",
    default=None,
    help="API key for authentication (optional, uses login if not provided).",
)
@click.option(
    "--username",
    default="astrbot",
    help="Username for login (if api-key not provided).",
)
@click.option(
    "--password",
    default="astrbot",
    help="Password for login (if api-key not provided).",
)
def tui(
    debug: bool,
    host: str,
    api_key: str | None,
    username: str,
    password: str,
) -> None:
    """
    Launch the AstrBot Terminal User Interface (TUI).

    This command starts an interactive terminal-based interface for AstrBot.
    The TUI connects to a running AstrBot instance via the dashboard API.
    """
    try:
        from astrbot.cli.commands.tui_async import run_tui_async

        run_tui_async(
            debug=debug,
            host=host,
            api_key=api_key,
            username=username,
            password=password,
        )
    except ImportError as e:
        click.echo(f"Error: Failed to import TUI module: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: Failed to start TUI: {e}", err=True)
        if debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)
