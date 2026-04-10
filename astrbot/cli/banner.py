"""ASCII logo and interactive mode utilities for CLI"""

import sys


logo_tmpl = r"""
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|
"""


def is_interactive() -> bool:
    """Check if stdout is connected to a TTY (interactive terminal)"""
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def print_logo() -> None:
    """Print ASCII logo if in interactive mode"""
    import click

    if is_interactive():
        click.echo(logo_tmpl)
