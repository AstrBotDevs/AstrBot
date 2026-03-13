"""AstrBot SDK 的命令行入口。"""

from __future__ import annotations

import asyncio
import sys
import typing
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import click
from loguru import logger

from .errors import AstrBotError
from .runtime.bootstrap import run_plugin_worker, run_supervisor, run_websocket_server
from .testing import (
    LocalRuntimeConfig,
    PluginHarness,
    StdoutPlatformSink,
    _PluginExecutionError,
    _PluginLoadError,
)

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_USAGE = 2
EXIT_PLUGIN_LOAD = 3
EXIT_RUNTIME = 4
EXIT_PLUGIN_EXECUTION = 5


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
    context: dict[str, Any] | None = None,
) -> None:
    log_method = getattr(logger, log_level)
    log_method(log_message)
    try:
        asyncio.run(entrypoint)
    except Exception as exc:
        exit_code, error_code, hint = _classify_cli_exception(exc)
        _render_cli_error(
            error_code=error_code,
            message=str(exc),
            hint=hint,
            context=context,
        )
        if exit_code == EXIT_UNEXPECTED:
            logger.exception("CLI 异常退出")
        raise SystemExit(exit_code) from exc


def _classify_cli_exception(exc: Exception) -> tuple[int, str, str]:
    if isinstance(exc, AstrBotError):
        return (
            EXIT_RUNTIME,
            exc.code,
            exc.hint or "请检查本地 mock core 与插件调用参数",
        )
    if isinstance(
        exc,
        (_PluginLoadError, FileNotFoundError, ImportError, ModuleNotFoundError),
    ):
        return (
            EXIT_PLUGIN_LOAD,
            "plugin_load_error",
            "请检查插件目录、plugin.yaml、requirements.txt 和导入路径",
        )
    if isinstance(exc, LookupError):
        return (
            EXIT_RUNTIME,
            "dispatch_error",
            "请检查 handler 或 capability 是否已正确注册",
        )
    if isinstance(exc, _PluginExecutionError):
        return (
            EXIT_PLUGIN_EXECUTION,
            "plugin_execution_error",
            "请检查插件生命周期、handler 或 capability 的实现",
        )
    return (
        EXIT_UNEXPECTED,
        "unexpected_error",
        "请查看详细日志，必要时使用 --verbose 重试",
    )


def _render_cli_error(
    *,
    error_code: str,
    message: str,
    hint: str = "",
    context: dict[str, Any] | None = None,
) -> None:
    click.echo(f"Error[{error_code}]: {message}", err=True)
    if hint:
        click.echo(f"Suggestion: {hint}", err=True)
    if not context:
        return
    for key, value in context.items():
        click.echo(f"{key}: {value}", err=True)


async def _run_local_dev(
    *,
    plugin_dir: Path,
    event_text: str | None,
    interactive: bool,
    session_id: str,
    user_id: str,
    platform: str,
    group_id: str | None,
    event_type: str,
) -> None:
    sink = StdoutPlatformSink(stream=sys.stdout)
    harness = PluginHarness(
        LocalRuntimeConfig(
            plugin_dir=plugin_dir,
            session_id=session_id,
            user_id=user_id,
            platform=platform,
            group_id=group_id,
            event_type=event_type,
        ),
        platform_sink=sink,
    )
    state = {
        "session_id": session_id,
        "user_id": user_id,
        "platform": platform,
        "group_id": group_id,
        "event_type": event_type,
    }
    async with harness:
        if interactive:
            click.echo(
                "本地交互模式已启动。可用命令：/session <id> /user <id> /platform <name> /group <id> /private /event <type> /exit"
            )
            while True:
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line:
                    break
                text = line.strip()
                if not text:
                    continue
                if _handle_dev_meta_command(text, state):
                    if text in {"/exit", "/quit"}:
                        break
                    continue
                await harness.dispatch_text(
                    text,
                    session_id=str(state["session_id"]),
                    user_id=str(state["user_id"]),
                    platform=str(state["platform"]),
                    group_id=typing.cast(str | None, state["group_id"]),
                    event_type=str(state["event_type"]),
                )
            return
        assert event_text is not None
        await harness.dispatch_text(
            event_text,
            session_id=session_id,
            user_id=user_id,
            platform=platform,
            group_id=group_id,
            event_type=event_type,
        )


def _handle_dev_meta_command(command: str, state: dict[str, Any]) -> bool:
    if command in {"/exit", "/quit"}:
        return True
    if command.startswith("/session "):
        state["session_id"] = command.split(" ", 1)[1].strip()
        click.echo(f"切换 session_id -> {state['session_id']}")
        return True
    if command.startswith("/user "):
        state["user_id"] = command.split(" ", 1)[1].strip()
        click.echo(f"切换 user_id -> {state['user_id']}")
        return True
    if command.startswith("/platform "):
        state["platform"] = command.split(" ", 1)[1].strip()
        click.echo(f"切换 platform -> {state['platform']}")
        return True
    if command.startswith("/group "):
        state["group_id"] = command.split(" ", 1)[1].strip()
        click.echo(f"切换 group_id -> {state['group_id']}")
        return True
    if command == "/private":
        state["group_id"] = None
        click.echo("已切换为私聊上下文")
        return True
    if command.startswith("/event "):
        state["event_type"] = command.split(" ", 1)[1].strip()
        click.echo(f"切换 event_type -> {state['event_type']}")
        return True
    return False


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
        context={"plugins_dir": plugins_dir},
    )


@cli.command()
@click.option(
    "--plugin-dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Plugin directory to run locally",
)
@click.option("--local", "local_mode", is_flag=True, help="Run against local mock core")
@click.option(
    "--standalone",
    "standalone_mode",
    is_flag=True,
    help="Alias of --local for compatibility",
)
@click.option("--event-text", type=str, help="Single message text to dispatch")
@click.option("--interactive", is_flag=True, help="Read follow-up messages from stdin")
@click.option("--session-id", default="local-session", show_default=True)
@click.option("--user-id", default="local-user", show_default=True)
@click.option("--platform", "platform_name", default="test", show_default=True)
@click.option("--group-id", default=None)
@click.option("--event-type", default="message", show_default=True)
def dev(
    plugin_dir: Path,
    local_mode: bool,
    standalone_mode: bool,
    event_text: str | None,
    interactive: bool,
    session_id: str,
    user_id: str,
    platform_name: str,
    group_id: str | None,
    event_type: str,
) -> None:
    """Run a plugin against the local mock core for development."""
    if not (local_mode or standalone_mode):
        raise click.BadParameter("当前 dev 只支持 --local/--standalone 模式")
    if interactive and event_text:
        raise click.BadParameter("--interactive 与 --event-text 不能同时使用")
    if not interactive and not event_text:
        raise click.BadParameter("请提供 --event-text，或改用 --interactive")
    _run_async_entrypoint(
        _run_local_dev(
            plugin_dir=plugin_dir,
            event_text=event_text,
            interactive=interactive,
            session_id=session_id,
            user_id=user_id,
            platform=platform_name,
            group_id=group_id,
            event_type=event_type,
        ),
        log_message=f"启动本地开发模式：{plugin_dir}",
        context={
            "plugin_dir": plugin_dir,
            "session_id": session_id,
            "platform": platform_name,
            "event_type": event_type,
        },
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
        context={"plugin_dir": plugin_dir},
    )


@cli.command(hidden=True)
@click.option("--port", default=8765, type=int, help="WebSocket server port")
def websocket(port: int) -> None:
    """Legacy websocket runtime entrypoint."""
    _run_async_entrypoint(
        run_websocket_server(port=port),
        log_message=f"启动 WebSocket 服务器，端口：{port}",
        context={"port": port},
    )
