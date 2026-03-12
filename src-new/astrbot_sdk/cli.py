# =============================================================================
# 新旧对比 - cli.py
# =============================================================================
#
# 【旧版 src/astrbot_sdk/cli/main.py】
# - 位于 cli/ 文件夹中
# - 有 setup_logger() 函数带 docstring
# - run 命令有 @click.pass_context 装饰器
# - plugins-dir 参数类型为 str
# - run 命令有 logger.info 输出
# - websocket 命令有 help 参数和 logger.info 输出
#
# 【新版 src-new/astrbot_sdk/cli.py】
# - 位于第一层，单文件
# - setup_logger() 无 docstring
# - run 命令无 @click.pass_context
# - plugins-dir 参数类型为 Path
# - 无日志输出
#
# =============================================================================
# TODO: 功能缺失
# =============================================================================
#
# 1. CLI 命令缺少 docstring
#    - 旧版 cli() 有 """AstrBot SDK CLI""" docstring
#    - 旧版 run() 有 """Start the plugin supervisor over stdio.""" docstring
#    - 旧版 worker() 有 """Internal command used by the supervisor to start a worker.""" docstring
#    - 旧版 websocket() 有 """Legacy websocket runtime entrypoint.""" docstring
#    - 新版所有命令都缺少 docstring
#
# 2. 缺少日志输出
#    - 旧版 run() 有 logger.info(f"Starting plugin supervisor with plugins dir: {plugins_dir}")
#    - 旧版 websocket() 有 logger.info(f"Starting WebSocket server on port {port}...")
#    - 新版无对应日志输出
#
# 3. websocket 命令缺少 help 参数
#    - 旧版: @click.option("--port", default=8765, help="WebSocket server port", type=int)
#    - 新版: @click.option("--port", default=8765, type=int)
#
# =============================================================================

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
