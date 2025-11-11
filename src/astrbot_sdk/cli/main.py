import asyncio
import sys
import click
from loguru import logger
from ..runtime.start_server import amain as run_server


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
@click.option("--port", default=8765, help="WebSocket server port", type=int)
@click.pass_context
def run(ctx, port: int):
    """Start the WebSocket server"""
    logger.info(f"Starting WebSocket server on port {port}...")
    asyncio.run(run_server(port))


if __name__ == "__main__":
    cli()
