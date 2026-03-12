"""AstrBot SDK 的命令行入口。"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import click
from loguru import logger

from .runtime.bootstrap import run_plugin_worker, run_supervisor, run_websocket_server


def setup_logger(verbose: bool = False) -> None:
    """初始化 CLI 使用的日志配置。"""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="DEBUG" if verbose else "INFO",
        colorize=True,
    )


def _run_async_entrypoint(
    entrypoint: Coroutine[Any, Any, object],
    *,
    log_message: str,
    log_level: str = "info",
) -> None:
    log_method = getattr(logger, log_level)
    log_method(log_message)
    asyncio.run(entrypoint)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, verbose: bool) -> None:
    """AstrBot SDK CLI。"""
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
    """Start the plugin supervisor over stdio."""
    _run_async_entrypoint(
        run_supervisor(plugins_dir=plugins_dir),
        log_message=f"启动插件主管进程，插件目录：{plugins_dir}",
    )


@cli.command(hidden=True)
@click.option(
    "--plugin-dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
)
def worker(plugin_dir: Path) -> None:
    """Internal command used by the supervisor to start a worker."""
    _run_async_entrypoint(
        run_plugin_worker(plugin_dir=plugin_dir),
        log_message=f"启动插件工作进程：{plugin_dir}",
        log_level="debug",
    )


@cli.command(hidden=True)
@click.option("--port", default=8765, type=int, help="WebSocket server port")
def websocket(port: int) -> None:
    """Legacy websocket runtime entrypoint."""
    _run_async_entrypoint(
        run_websocket_server(port=port),
        log_message=f"启动 WebSocket 服务器，端口：{port}",
    )
