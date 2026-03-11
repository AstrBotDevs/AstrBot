import asyncio
import sys

import click
from loguru import logger

from ..runtime.serve import run_plugin_worker, run_supervisor, run_websocket_server


def setup_logger(verbose: bool = False):
    """Configure loguru for CLI output"""
    # Remove default handler
    logger.remove()

    # Add custom handler with CLI-friendly format
    log_format = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<level>{message}</level>"
    )

    level = "DEBUG" if verbose else "INFO"

    logger.add(
        sys.stderr,
        format=log_format,
        level=level,
        colorize=True,
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, verbose):
    """AstrBot SDK CLI"""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logger(verbose)


@cli.command()
@click.option(
    "--plugins-dir",
    default="plugins",
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    help="Directory containing plugin folders",
)
@click.pass_context
def run(ctx, plugins_dir: str):
    """Start the plugin supervisor over stdio."""
    logger.info(f"Starting plugin supervisor with plugins dir: {plugins_dir}")
    asyncio.run(run_supervisor(plugins_dir=plugins_dir))


@cli.command(hidden=True)
@click.option(
    "--plugin-dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
)
def worker(plugin_dir: str):
    """Internal command used by the supervisor to start a worker."""
    asyncio.run(run_plugin_worker(plugin_dir=plugin_dir))


@cli.command(hidden=True)
@click.option("--port", default=8765, help="WebSocket server port", type=int)
def websocket(port: int):
    """Legacy websocket runtime entrypoint."""
    logger.info(f"Starting WebSocket server on port {port}...")
    asyncio.run(run_websocket_server(port=port))


if __name__ == "__main__":
    cli()
