from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from loguru import logger

from .runtime.bootstrap import run_plugin_worker, run_supervisor, run_websocket_server


def setup_logger(verbose: bool = False) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="DEBUG" if verbose else "INFO",
        colorize=True,
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, verbose: bool) -> None:
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logger(verbose)


@cli.command()
@click.option(
    "--plugins-dir",
    default="plugins",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Directory containing plugin folders",
)
def run(plugins_dir: Path) -> None:
    asyncio.run(run_supervisor(plugins_dir=plugins_dir))


@cli.command(hidden=True)
@click.option(
    "--plugin-dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
)
def worker(plugin_dir: Path) -> None:
    asyncio.run(run_plugin_worker(plugin_dir=plugin_dir))


@cli.command(hidden=True)
@click.option("--port", default=8765, type=int)
def websocket(port: int) -> None:
    asyncio.run(run_websocket_server(port=port))
