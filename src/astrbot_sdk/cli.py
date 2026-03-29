"""AstrBot SDK 的命令行入口。

本模块提供 astrbot-sdk 命令行工具的所有子命令，包括：
- init: 创建新插件骨架，生成 plugin.yaml、main.py、README.md 等模板文件
- validate: 校验插件清单、导入路径和 handler 发现是否正常
- build: 将插件打包为 .zip 发布包
- dev: 本地开发模式，支持 --local/--watch/--interactive 等调试选项
- run: 启动插件主管进程（supervisor），通过 stdio 与 AstrBot 核心通信
- worker: 内部命令，由 supervisor 调用以启动单个插件工作进程

错误处理：
所有 CLI 异常都会被分类并返回标准化的退出码和错误提示，
便于 CI/CD 集成和用户快速定位问题。
"""

from __future__ import annotations

import asyncio
import importlib.resources as resources
import os
import re
import sys
import typing
import zipfile
from collections.abc import Coroutine
from dataclasses import dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path
from textwrap import dedent
from typing import Any

import click

from ._internal.sdk_logger import logger
from .errors import AstrBotError
from .runtime.bootstrap import run_plugin_worker, run_supervisor, run_websocket_server
from .runtime.loader import load_plugin, load_plugin_spec, validate_plugin_spec

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_USAGE = 2
EXIT_PLUGIN_LOAD = 3
EXIT_RUNTIME = 4
EXIT_PLUGIN_EXECUTION = 5
BUILD_EXCLUDED_DIRS = {
    ".agents",
    ".claude",
    ".git",
    ".idea",
    ".mypy_cache",
    ".opencode",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
}
BUILD_EXCLUDED_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    ".astrbot-worker-state.json",
}
WATCH_POLL_INTERVAL_SECONDS = 0.5
SUPPORTED_INIT_AGENTS = ("claude", "codex", "opencode")
_TEMPLATE_VARIABLE_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
INIT_AGENT_SKILL_ROOTS = {
    "claude": Path(".claude") / "skills",
    "codex": Path(".agents") / "skills",
    "opencode": Path(".opencode") / "skills",
}
INIT_AGENT_DISPLAY_NAMES = {
    "claude": "Claude Code",
    "codex": "Codex",
    "opencode": "OpenCode",
}
INIT_SKILL_TEMPLATE_NAME = "astrbot-plugin-dev"
INIT_PROJECT_NOTE_TEMPLATE_DIR = ("templates", "project_notes")
INIT_PROJECT_NOTE_TEMPLATE_NAMES = ("AGENTS.md", "CLAUDE.md")


class _CliPluginValidationError(RuntimeError):
    """CLI 侧的插件结构或打包校验失败。"""


class _CliPluginLoadError(RuntimeError):
    """CLI 侧的本地开发插件加载失败。"""


class _CliPluginExecutionError(RuntimeError):
    """CLI 侧的本地开发插件执行失败。"""


@dataclass(slots=True)
class _PluginTreeWatcher:
    plugin_dir: Path
    snapshot: dict[str, tuple[int, int]] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.snapshot = _snapshot_watch_files(self.plugin_dir)

    def poll_changes(self) -> list[str]:
        current = _snapshot_watch_files(self.plugin_dir)
        changed = sorted(
            path
            for path in set(self.snapshot) | set(current)
            if self.snapshot.get(path) != current.get(path)
        )
        self.snapshot = current
        return changed


def setup_logger(verbose: bool = False) -> None:
    """初始化 CLI 使用的日志配置。"""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="DEBUG" if verbose else "INFO",
        colorize=True,
    )


def _resolve_protocol_stdout(
    protocol_stdout: str | None,
) -> tuple[typing.TextIO, typing.TextIO | None]:
    configured = str(protocol_stdout).strip() if protocol_stdout is not None else ""
    if not configured:
        stdout = sys.stdout
        if callable(getattr(stdout, "isatty", None)) and stdout.isatty():
            opened_stdout = open(os.devnull, "w", encoding="utf-8")
            return opened_stdout, opened_stdout
        return stdout, None
    if configured.lower() == "console":
        return sys.stdout, None
    output_path = os.devnull if configured.lower() == "silent" else configured
    opened_stdout = open(output_path, "w", encoding="utf-8")
    return opened_stdout, opened_stdout


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
    except (click.Abort, KeyboardInterrupt):
        click.echo("\n创建插件已优雅地中断。", err=True)
        raise SystemExit(130)
    except Exception as exc:
        exit_code, error_code, hint = _classify_cli_exception(exc)
        docs_url = exc.docs_url if isinstance(exc, AstrBotError) else ""
        details = exc.details if isinstance(exc, AstrBotError) else None
        _render_cli_error(
            error_code=error_code,
            message=str(exc),
            hint=hint,
            docs_url=docs_url,
            details=details,
            context=context,
        )
        if exit_code == EXIT_UNEXPECTED:
            logger.exception("CLI 异常退出")
        raise SystemExit(exit_code) from exc


def _run_sync_entrypoint(
    entrypoint: typing.Callable[[], object],
    *,
    log_message: str,
    log_level: str = "info",
    context: dict[str, Any] | None = None,
) -> None:
    log_method = getattr(logger, log_level)
    log_method(log_message)
    try:
        entrypoint()
    except (click.Abort, KeyboardInterrupt):
        click.echo("\n创建插件已优雅地中断。", err=True)
        raise SystemExit(130)
    except Exception as exc:
        exit_code, error_code, hint = _classify_cli_exception(exc)
        docs_url = exc.docs_url if isinstance(exc, AstrBotError) else ""
        details = exc.details if isinstance(exc, AstrBotError) else None
        _render_cli_error(
            error_code=error_code,
            message=str(exc),
            hint=hint,
            docs_url=docs_url,
            details=details,
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
        (
            _CliPluginValidationError,
            _CliPluginLoadError,
            FileNotFoundError,
            ImportError,
            ModuleNotFoundError,
        ),
    ):
        return (
            EXIT_PLUGIN_LOAD,
            "plugin_load_error",
            "请检查插件目录、plugin.yaml、requirements.txt（如有）和导入路径",
        )
    if isinstance(exc, LookupError):
        return (
            EXIT_RUNTIME,
            "dispatch_error",
            "请检查 handler 或 capability 是否已正确注册",
        )
    if isinstance(exc, _CliPluginExecutionError):
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
    docs_url: str = "",
    details: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    click.echo(f"Error[{error_code}]: {message}", err=True)
    if hint:
        click.echo(f"Suggestion: {hint}", err=True)
    if docs_url:
        click.echo(f"Docs: {docs_url}", err=True)
    if details:
        click.echo(f"Details: {details}", err=True)
    if not context:
        return
    for key, value in context.items():
        click.echo(f"{key}: {value}", err=True)


def _render_nonfatal_dev_error(
    exc: Exception,
    *,
    context: dict[str, Any] | None = None,
) -> None:
    exit_code, error_code, hint = _classify_cli_exception(exc)
    _render_cli_error(
        error_code=error_code,
        message=str(exc),
        hint=hint,
        context=context,
    )
    if exit_code == EXIT_UNEXPECTED:
        logger.exception("watch 模式收到未分类异常")


def _iter_watch_files(plugin_dir: Path) -> typing.Iterator[Path]:
    root = plugin_dir.resolve()
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(root)
        if any(part in BUILD_EXCLUDED_DIRS for part in relative.parts[:-1]):
            continue
        if relative.name in BUILD_EXCLUDED_FILES:
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        yield path


def _snapshot_watch_files(plugin_dir: Path) -> dict[str, tuple[int, int]]:
    root = plugin_dir.resolve()
    snapshot: dict[str, tuple[int, int]] = {}
    for path in _iter_watch_files(root):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        snapshot[path.relative_to(root).as_posix()] = (
            stat.st_mtime_ns,
            stat.st_size,
        )
    return snapshot


def _format_watch_changes(changes: list[str], *, limit: int = 5) -> str:
    if not changes:
        return "未知文件"
    preview = changes[:limit]
    text = ", ".join(preview)
    if len(changes) > limit:
        text += f" 等 {len(changes)} 个文件"
    return text


class _ReloadableLocalDevRunner:
    def __init__(
        self,
        *,
        plugin_dir: Path,
        state: dict[str, Any],
        plugin_load_error: type[Exception],
        plugin_execution_error: type[Exception],
        plugin_harness,
        stdout_platform_sink,
    ) -> None:
        self.plugin_dir = plugin_dir
        self.state = state
        self._plugin_load_error = plugin_load_error
        self._plugin_execution_error = plugin_execution_error
        self._plugin_harness = plugin_harness
        self._stdout_platform_sink = stdout_platform_sink
        self._harness = None
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        async with self._lock:
            await self._stop_harness()

    async def reload(self) -> bool:
        async with self._lock:
            await self._stop_harness()
            harness = self._plugin_harness.from_plugin_dir(
                self.plugin_dir,
                session_id=str(self.state["session_id"]),
                user_id=str(self.state["user_id"]),
                platform=str(self.state["platform"]),
                group_id=typing.cast(str | None, self.state["group_id"]),
                event_type=str(self.state["event_type"]),
                platform_sink=self._stdout_platform_sink(stream=sys.stdout),
            )
            try:
                await harness.start()
            except self._plugin_load_error as exc:
                _render_nonfatal_dev_error(
                    _CliPluginLoadError(str(exc)),
                    context={"plugin_dir": self.plugin_dir},
                )
                return False
            except self._plugin_execution_error as exc:
                _render_nonfatal_dev_error(
                    _CliPluginExecutionError(str(exc)),
                    context={"plugin_dir": self.plugin_dir},
                )
                return False
            self._harness = harness
            return True

    async def dispatch_text(self, text: str) -> bool:
        async with self._lock:
            if self._harness is None:
                click.echo("当前插件未成功加载，等待下一次文件变更后重试。")
                return False
            try:
                await self._harness.dispatch_text(
                    text,
                    session_id=str(self.state["session_id"]),
                    user_id=str(self.state["user_id"]),
                    platform=str(self.state["platform"]),
                    group_id=typing.cast(str | None, self.state["group_id"]),
                    event_type=str(self.state["event_type"]),
                )
            except (self._plugin_load_error, self._plugin_execution_error) as exc:
                _render_nonfatal_dev_error(
                    _CliPluginExecutionError(str(exc)),
                    context={"plugin_dir": self.plugin_dir},
                )
                return False
            except Exception as exc:
                _render_nonfatal_dev_error(
                    exc,
                    context={"plugin_dir": self.plugin_dir},
                )
                return False
            return True

    async def _stop_harness(self) -> None:
        if self._harness is None:
            return
        try:
            await self._harness.stop()
        finally:
            self._harness = None


async def _run_local_dev_watch(
    *,
    runner: _ReloadableLocalDevRunner,
    event_text: str | None,
    interactive: bool,
    watch_poll_interval: float,
    max_watch_reloads: int | None = None,
) -> None:
    watcher = _PluginTreeWatcher(runner.plugin_dir)
    reload_count = 0

    async def reload_and_maybe_rerun(*, announce: str | None) -> None:
        if announce:
            click.echo(announce)
        if not await runner.reload():
            return
        if event_text is not None:
            await runner.dispatch_text(event_text)

    async def watch_loop(stop_event: asyncio.Event) -> None:
        nonlocal reload_count
        while not stop_event.is_set():
            await asyncio.sleep(watch_poll_interval)
            changes = watcher.poll_changes()
            if not changes:
                continue
            await reload_and_maybe_rerun(
                announce=(
                    f"检测到文件变更，重新加载插件：{_format_watch_changes(changes)}"
                )
            )
            reload_count += 1
            if max_watch_reloads is not None and reload_count >= max_watch_reloads:
                stop_event.set()
                return

    stop_event = asyncio.Event()
    watch_task: asyncio.Task[None] | None = None
    try:
        await reload_and_maybe_rerun(
            announce=(
                "watch 模式已启动，监听插件目录变更。"
                if event_text is not None
                else "watch 模式已启动，监听插件目录变更并按需热重载。"
            )
        )
        if max_watch_reloads == 0:
            return
        watch_task = asyncio.create_task(watch_loop(stop_event))
        if interactive:
            click.echo(
                "本地交互模式已启动。可用命令：/session <id> /user <id> /platform <name> /group <id> /private /event <type> /exit"
            )
            while not stop_event.is_set():
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line:
                    break
                text = line.strip()
                if not text:
                    continue
                if _handle_dev_meta_command(text, runner.state):
                    if text in {"/exit", "/quit"}:
                        break
                    continue
                await runner.dispatch_text(text)
            stop_event.set()
            return
        await stop_event.wait()
    finally:
        stop_event.set()
        if watch_task is not None:
            watch_task.cancel()
            try:
                await watch_task
            except asyncio.CancelledError:
                pass
        await runner.close()


async def _run_local_dev(
    *,
    plugin_dir: Path,
    event_text: str | None,
    interactive: bool,
    watch: bool,
    session_id: str,
    user_id: str,
    platform: str,
    group_id: str | None,
    event_type: str,
    watch_poll_interval: float = WATCH_POLL_INTERVAL_SECONDS,
    max_watch_reloads: int | None = None,
) -> None:
    from .testing import (
        PluginHarness,
        StdoutPlatformSink,
        _PluginExecutionError,
        _PluginLoadError,
    )

    state = {
        "session_id": session_id,
        "user_id": user_id,
        "platform": platform,
        "group_id": group_id,
        "event_type": event_type,
    }
    if watch:
        runner = _ReloadableLocalDevRunner(
            plugin_dir=plugin_dir,
            state=state,
            plugin_load_error=_PluginLoadError,
            plugin_execution_error=_PluginExecutionError,
            plugin_harness=PluginHarness,
            stdout_platform_sink=StdoutPlatformSink,
        )
        await _run_local_dev_watch(
            runner=runner,
            event_text=event_text,
            interactive=interactive,
            watch_poll_interval=watch_poll_interval,
            max_watch_reloads=max_watch_reloads,
        )
        return

    sink = StdoutPlatformSink(stream=sys.stdout)
    harness = PluginHarness.from_plugin_dir(
        plugin_dir,
        session_id=session_id,
        user_id=user_id,
        platform=platform,
        group_id=group_id,
        event_type=event_type,
        platform_sink=sink,
    )
    try:
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
    except _PluginLoadError as exc:
        raise _CliPluginLoadError(str(exc)) from exc
    except _PluginExecutionError as exc:
        raise _CliPluginExecutionError(str(exc)) from exc


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


def _slugify_plugin_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "my_plugin"


def _normalize_plugin_name(value: str) -> str:
    normalized = _slugify_plugin_name(value)
    if normalized.startswith("astrbot_plugin_"):
        return normalized
    normalized = normalized.removeprefix("astrbot_plugin")
    normalized = normalized.strip("_")
    suffix = normalized or "my_plugin"
    return f"astrbot_plugin_{suffix}"


def _class_name_for_plugin(value: str) -> str:
    parts = [part for part in re.split(r"[^a-zA-Z0-9]+", value) if part]
    if not parts:
        return "MyPlugin"
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _sanitize_build_part(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("._-")
    return sanitized or "artifact"


def _parse_init_agents(
    _ctx: click.Context,
    _param: click.Parameter,
    value: str | None,
) -> tuple[str, ...]:
    if value is None:
        return ()

    normalized_agents: list[str] = []
    seen: set[str] = set()
    invalid_agents: list[str] = []
    for raw_agent in value.split(","):
        candidate = raw_agent.strip().lower()
        if not candidate:
            invalid_agents.append("<empty>")
            continue
        if candidate not in SUPPORTED_INIT_AGENTS:
            invalid_agents.append(raw_agent.strip())
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized_agents.append(candidate)

    if invalid_agents:
        supported = ", ".join(SUPPORTED_INIT_AGENTS)
        invalid = ", ".join(invalid_agents)
        raise click.BadParameter(f"仅支持以下 agent: {supported}；非法值: {invalid}")
    return tuple(normalized_agents)


def _render_init_plugin_yaml(
    *,
    plugin_name: str,
    display_name: str,
    desc: str,
    author: str,
    repo: str,
    version: str,
) -> str:
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    class_name = _class_name_for_plugin(plugin_name)
    return dedent(
        f"""\
        name: {plugin_name}
        display_name: {display_name}
        desc: {desc}
        author: {author}
        repo: {repo}
        version: {version}
        runtime:
          python: "{python_version}"
        components:
          - class: main:{class_name}
        """
    )


def _render_init_main_py(*, plugin_name: str) -> str:
    class_name = _class_name_for_plugin(plugin_name)
    return dedent(
        f"""\
        from astrbot_sdk import Context, MessageEvent, Star, on_command


        class {class_name}(Star):
            @on_command("hello")
            async def hello(self, event: MessageEvent, ctx: Context) -> None:
                await event.reply("Hello, World!")
        """
    )


def _render_init_readme(*, plugin_name: str) -> str:
    return dedent(
        f"""\
        # {plugin_name}

        一个最小可运行的 AstrBot SDK v4 插件。

        ## 目录结构

        ```
        .
        ├── plugin.yaml
        ├── requirements.txt
        ├── main.py
        └── tests
            └── test_plugin.py
        ```

        ## 本地开发

        ```bash
        astrbot-sdk validate
        astrbot-sdk dev --local --event-text hello
        astrbot-sdk dev --local --watch --event-text hello
        ```

        ## 运行测试

        ```bash
        python -m pytest tests/test_plugin.py -v
        ```
        """
    )


def _render_init_gitignore() -> str:
    return dedent(
        """\
        # Python
        __pycache__/
        *.py[cod]
        *.pyo
        *.egg-info/
        dist/
        build/
        *.egg

        # 虚拟环境
        .venv/
        venv/
        env/

        # IDE
        .idea/
        .vscode/
        *.swp
        *.swo
        *~

        # OS
        .DS_Store
        Thumbs.db
        desktop.ini

        # 测试 / 检查缓存
        .pytest_cache/
        .ruff_cache/
        .mypy_cache/
        .coverage
        htmlcov/

        # 开发/构建工具
        /.claude/
        /.agents/
        /.opencode/

        # 图床配置（含 API 密钥等敏感信息）
        /image_host/config.json

        # 插件测试产物
        /.astrbot_sdk_testing/
        """
    )


def _render_init_test_py(*, plugin_name: str) -> str:
    class_name = _class_name_for_plugin(plugin_name)
    return dedent(
        f"""\
        from pathlib import Path

        import pytest

        from astrbot_sdk.testing import MockContext, MockMessageEvent, PluginHarness
        from main import {class_name}


        @pytest.mark.asyncio
        async def test_hello_handler():
            plugin = {class_name}()
            ctx = MockContext(
                plugin_id="{plugin_name}",
                plugin_metadata={{"display_name": "{class_name}"}},
            )
            event = MockMessageEvent(text="/hello", context=ctx)

            await plugin.hello(event, ctx)

            assert event.replies == ["Hello, World!"]
            ctx.platform.assert_sent("Hello, World!")


        @pytest.mark.asyncio
        async def test_hello_dispatch():
            plugin_dir = Path(__file__).resolve().parents[1]

            async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
                records = await harness.dispatch_text("hello")

            assert any(record.text == "Hello, World!" for record in records)
        """
    )


def _plugin_root_hint_for_agent(agent: str) -> str:
    skill_dir = INIT_AGENT_SKILL_ROOTS[agent] / INIT_SKILL_TEMPLATE_NAME
    return "/".join(".." for _ in skill_dir.parts) or "."


def _build_agent_template_context(
    *,
    plugin_name: str,
    display_name: str,
    agent: str,
) -> dict[str, str]:
    return {
        "plugin_name": plugin_name,
        "display_name": display_name,
        "class_name": _class_name_for_plugin(plugin_name),
        "skill_name": f"{plugin_name}_project",
        "plugin_root": _plugin_root_hint_for_agent(agent),
        "agent_name": agent,
        "agent_display_name": INIT_AGENT_DISPLAY_NAMES[agent],
        "skill_dir_name": INIT_SKILL_TEMPLATE_NAME,
    }


def _render_template_text(template_text: str, context: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise _CliPluginValidationError(f"agent 模板变量未定义：{key}")
        return context[key]

    return _TEMPLATE_VARIABLE_PATTERN.sub(replace, template_text)


def _copy_rendered_template_tree(
    source_dir: Traversable,
    target_dir: Path,
    *,
    context: dict[str, str],
) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source_dir.iterdir(), key=lambda item: item.name):
        destination = target_dir / entry.name
        if entry.is_dir():
            _copy_rendered_template_tree(entry, destination, context=context)
            continue
        destination.write_text(
            _render_template_text(entry.read_text(encoding="utf-8"), context),
            encoding="utf-8",
        )


def _render_init_agent_templates(
    *,
    target_dir: Path,
    plugin_name: str,
    display_name: str,
    agents: tuple[str, ...],
) -> None:
    if not agents:
        return

    template_root = resources.files("astrbot_sdk").joinpath(
        "templates",
        "skills",
        INIT_SKILL_TEMPLATE_NAME,
    )
    if not template_root.is_dir():
        raise _CliPluginValidationError(
            f"未找到项目级 skill 模板：{INIT_SKILL_TEMPLATE_NAME}"
        )

    for agent in agents:
        context = _build_agent_template_context(
            plugin_name=plugin_name,
            display_name=display_name,
            agent=agent,
        )
        _copy_rendered_template_tree(
            template_root,
            target_dir / INIT_AGENT_SKILL_ROOTS[agent] / INIT_SKILL_TEMPLATE_NAME,
            context=context,
        )


def _render_init_project_notes(*, target_dir: Path) -> None:
    template_root = resources.files("astrbot_sdk").joinpath(
        *INIT_PROJECT_NOTE_TEMPLATE_DIR
    )
    if not template_root.is_dir():
        raise _CliPluginValidationError("未找到项目级说明模板：AGENTS.md / CLAUDE.md")

    for template_name in INIT_PROJECT_NOTE_TEMPLATE_NAMES:
        template_path = template_root.joinpath(template_name)
        if not template_path.is_file():
            raise _CliPluginValidationError(
                f"未找到项目级说明模板文件：{template_name}"
            )
        # Keep these notes as packaged resources so `astr init` behaves the same
        # from a repo checkout, an sdist, and an installed wheel.
        (target_dir / template_name).write_text(
            template_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def _ensure_plugin_dir_exists(plugin_dir: Path) -> Path:
    resolved = plugin_dir.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise _CliPluginValidationError(f"插件目录不存在：{plugin_dir}")
    return resolved


def _resolve_dev_plugin_dir(plugin_dir: Path | None) -> Path:
    if plugin_dir is not None:
        return plugin_dir
    current_dir = Path.cwd()
    if (current_dir / "plugin.yaml").exists():
        return Path(".")
    raise click.BadParameter(
        "未提供 --plugin-dir，且当前目录未找到 plugin.yaml",
        param_hint="--plugin-dir",
    )


def _load_validated_plugin(plugin_dir: Path) -> tuple[Any, Any]:
    resolved_dir = _ensure_plugin_dir_exists(plugin_dir)
    plugin = load_plugin_spec(resolved_dir)
    try:
        validate_plugin_spec(plugin)
    except ValueError as exc:
        raise _CliPluginValidationError(str(exc)) from exc

    loaded = load_plugin(plugin)
    if not loaded.instances:
        raise _CliPluginValidationError(
            "未找到可加载的组件，请检查 plugin.yaml 中的 components"
        )
    return plugin, loaded


def _build_kind(plugin: Any) -> str:
    return (
        "legacy-main"
        if bool(plugin.manifest_data.get("__legacy_main__"))
        else "plugin-yaml"
    )


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _iter_build_files(plugin_dir: Path, output_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(plugin_dir.rglob("*")):
        if path.is_dir():
            continue
        if _path_is_within(path, output_dir):
            continue
        relative = path.relative_to(plugin_dir)
        if any(part in BUILD_EXCLUDED_DIRS for part in relative.parts[:-1]):
            continue
        if relative.name in BUILD_EXCLUDED_FILES:
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        files.append(path)
    return files


def _prompt_nonempty_text(prompt: str) -> str:
    while True:
        value = click.prompt(prompt, type=str, default="", show_default=False).strip()
        if value:
            return value
        click.echo("该字段不能为空，请重新输入。")


def _default_init_repo_name(plugin_name: str) -> str:
    return _normalize_plugin_name(plugin_name)


def _collect_init_metadata(name: str | None) -> tuple[str, str, str, str, str]:
    plugin_name = name if name is not None else _prompt_nonempty_text("插件名字")
    author = _prompt_nonempty_text("作者")
    repo = _default_init_repo_name(plugin_name)
    desc = click.prompt("描述", type=str, default="", show_default=False).strip()
    version = click.prompt("版本", type=str, default="1.0.0", show_default=True).strip()
    return plugin_name, author, repo, desc, version or "1.0.0"


def _init_plugin(name: str | None, agents: tuple[str, ...] = ()) -> None:
    raw_name, author, repo, desc, version = _collect_init_metadata(name)
    plugin_name = _normalize_plugin_name(raw_name)
    target_dir = Path(plugin_name)
    if target_dir.exists():
        raise _CliPluginValidationError(f"目标目录已存在：{target_dir}")

    display_name = raw_name.strip() or plugin_name
    target_dir.mkdir(parents=True, exist_ok=False)
    (target_dir / "tests").mkdir()
    (target_dir / "plugin.yaml").write_text(
        _render_init_plugin_yaml(
            plugin_name=plugin_name,
            display_name=display_name,
            desc=desc,
            author=author,
            repo=repo,
            version=version,
        ),
        encoding="utf-8",
    )
    (target_dir / "requirements.txt").write_text("", encoding="utf-8")
    (target_dir / "main.py").write_text(
        _render_init_main_py(plugin_name=plugin_name),
        encoding="utf-8",
    )
    (target_dir / "README.md").write_text(
        _render_init_readme(plugin_name=plugin_name),
        encoding="utf-8",
    )
    (target_dir / ".gitignore").write_text(
        _render_init_gitignore(),
        encoding="utf-8",
    )
    (target_dir / "tests" / "test_plugin.py").write_text(
        _render_init_test_py(plugin_name=plugin_name),
        encoding="utf-8",
    )
    _render_init_project_notes(target_dir=target_dir)
    _render_init_agent_templates(
        target_dir=target_dir,
        plugin_name=plugin_name,
        display_name=display_name,
        agents=agents,
    )

    import subprocess

    try:
        process = subprocess.run(
            ["git", "init", str(target_dir)],
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            stderr = process.stderr.strip()
            raise RuntimeError(
                f"Git 初始化失败（退出码 {process.returncode}）"
                + (f": {stderr}" if stderr else "")
            )
        click.echo(f"Git 仓库已初始化: {target_dir}")
    except FileNotFoundError:
        click.echo("警告: 未找到 git 命令，请先安装 git 后手动执行 git init")
    except RuntimeError as e:
        click.echo(f"警告: {e}")

    click.echo(f"已创建插件：{target_dir}")
    if agents:
        generated_paths = ", ".join(
            str(INIT_AGENT_SKILL_ROOTS[agent] / INIT_SKILL_TEMPLATE_NAME)
            for agent in agents
        )
        click.echo(f"已生成项目级 skill：{generated_paths}")
    click.echo("后续命令：")
    click.echo(f"  astrbot-sdk validate --plugin-dir {target_dir}")
    click.echo(
        f"  astrbot-sdk dev --local --plugin-dir {target_dir} --event-text hello"
    )


def _validate_plugin(plugin_dir: Path) -> None:
    plugin, loaded = _load_validated_plugin(plugin_dir)
    click.echo(f"校验通过：{plugin.name}")
    click.echo(f"kind: {_build_kind(plugin)}")
    click.echo(f"plugin_dir: {plugin.plugin_dir}")
    click.echo(f"handlers: {len(loaded.handlers)}")
    click.echo(f"capabilities: {len(loaded.capabilities)}")
    click.echo(f"instances: {len(loaded.instances)}")


def _build_plugin(plugin_dir: Path, output_dir: Path | None) -> None:
    plugin, _ = _load_validated_plugin(plugin_dir)
    build_dir = (output_dir or (plugin.plugin_dir / "dist")).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    version = _sanitize_build_part(str(plugin.manifest_data.get("version") or "0.0.0"))
    archive_name = f"{_sanitize_build_part(plugin.name)}-{version}.zip"
    archive_path = build_dir / archive_name

    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for path in _iter_build_files(plugin.plugin_dir, build_dir):
            archive.write(path, arcname=path.relative_to(plugin.plugin_dir))

    click.echo(f"构建完成：{archive_path}")
    click.echo(f"artifact: {archive_path}")


def _run_websocket_worker_entrypoint(
    *,
    worker_id: str | None,
    plugin_dirs: tuple[Path, ...],
    host: str,
    port: int,
    path: str,
    tls_ca_file: Path,
    tls_cert_file: Path,
    tls_key_file: Path,
) -> None:
    resolved_plugin_dirs = list(plugin_dirs) if plugin_dirs else [Path.cwd()]
    _run_async_entrypoint(
        run_websocket_server(
            worker_id=worker_id,
            plugin_dirs=resolved_plugin_dirs,
            host=host,
            port=port,
            path=path,
            tls_ca_file=tls_ca_file,
            tls_cert_file=tls_cert_file,
            tls_key_file=tls_key_file,
        ),
        log_message=f"启动 WebSocket Worker，端口：{port}",
        context={
            "worker_id": worker_id,
            "plugin_dirs": resolved_plugin_dirs,
            "port": port,
            "path": path,
        },
    )


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
@click.option(
    "--workers-manifest",
    default=None,
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    help="Supervisor manifest describing remote websocket workers",
)
@click.option(
    "--protocol-stdout",
    default=None,
    type=str,
    help="Redirect runtime protocol stdout to console, silent, or a file path",
)
def run(
    plugins_dir: Path,
    workers_manifest: Path | None,
    protocol_stdout: str | None,
) -> None:
    """Start the plugin supervisor over stdio."""
    transport_stdout, opened_stdout = _resolve_protocol_stdout(protocol_stdout)
    try:
        _run_async_entrypoint(
            run_supervisor(
                plugins_dir=plugins_dir,
                stdout=transport_stdout,
                workers_manifest=workers_manifest,
            ),
            log_message=f"启动插件主管进程，插件目录：{plugins_dir}",
            context={
                "plugins_dir": plugins_dir,
                "workers_manifest": workers_manifest,
            },
        )
    finally:
        if opened_stdout is not None:
            opened_stdout.close()


@cli.command()
@click.argument("name", type=str, required=False)
@click.option(
    "--agents",
    callback=_parse_init_agents,
    metavar="claude,codex,opencode",
    help="Generate per-agent project templates, comma-separated: claude,codex,opencode",
)
def init(name: str | None, agents: tuple[str, ...]) -> None:
    """Create a new plugin skeleton in the target directory."""
    _run_sync_entrypoint(
        lambda: _init_plugin(name, agents),
        log_message=f"创建插件：{name or '<interactive>'}",
        context={"target": name or "<interactive>"},
    )


@cli.command()
@click.option(
    "--plugin-dir",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Plugin directory to validate",
)
def validate(plugin_dir: Path) -> None:
    """Validate plugin manifest, imports and handler discovery."""
    _run_sync_entrypoint(
        lambda: _validate_plugin(plugin_dir),
        log_message=f"校验插件目录：{plugin_dir}",
        context={"plugin_dir": plugin_dir},
    )


@cli.command()
@click.option(
    "--plugin-dir",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Plugin directory to package",
)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Directory for the build artifact, defaults to <plugin-dir>/dist",
)
def build(plugin_dir: Path, output_dir: Path | None) -> None:
    """Validate and package a plugin into a zip artifact."""
    _run_sync_entrypoint(
        lambda: _build_plugin(plugin_dir, output_dir),
        log_message=f"构建插件包：{plugin_dir}",
        context={"plugin_dir": plugin_dir, "output_dir": output_dir},
    )


@cli.command()
@click.option(
    "--plugin-dir",
    required=False,
    default=None,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Plugin directory to run locally, defaults to current directory when plugin.yaml exists",
)
@click.option("--local", "local_mode", is_flag=True, help="Run against local mock core")
@click.option(
    "--standalone",
    "standalone_mode",
    is_flag=True,
    help="Deprecated alias of --local",
)
@click.option("--event-text", type=str, help="Single message text to dispatch")
@click.option("--interactive", is_flag=True, help="Read follow-up messages from stdin")
@click.option(
    "--watch",
    is_flag=True,
    help="Reload the local harness when plugin files change",
)
@click.option("--session-id", default="local-session", show_default=True)
@click.option("--user-id", default="local-user", show_default=True)
@click.option("--platform", "platform_name", default="test", show_default=True)
@click.option("--group-id", default=None)
@click.option("--event-type", default="message", show_default=True)
def dev(
    plugin_dir: Path | None,
    local_mode: bool,
    standalone_mode: bool,
    event_text: str | None,
    interactive: bool,
    watch: bool,
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
    resolved_plugin_dir = _resolve_dev_plugin_dir(plugin_dir)
    _run_async_entrypoint(
        _run_local_dev(
            plugin_dir=resolved_plugin_dir,
            event_text=event_text,
            interactive=interactive,
            watch=watch,
            session_id=session_id,
            user_id=user_id,
            platform=platform_name,
            group_id=group_id,
            event_type=event_type,
        ),
        log_message=f"启动本地开发模式：{resolved_plugin_dir}",
        context={
            "plugin_dir": resolved_plugin_dir,
            "session_id": session_id,
            "platform": platform_name,
            "event_type": event_type,
        },
    )


@cli.command(hidden=True)
@click.option(
    "--plugin-dir",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "--group-metadata",
    required=False,
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--protocol-stdout",
    default=None,
    type=str,
    help="Redirect runtime protocol stdout to console, silent, or a file path",
)
def worker(
    plugin_dir: Path | None,
    group_metadata: Path | None,
    protocol_stdout: str | None,
) -> None:
    """Internal command used by the supervisor to start a worker."""
    if plugin_dir is None and group_metadata is None:
        raise click.UsageError("Either --plugin-dir or --group-metadata is required")
    if plugin_dir is not None and group_metadata is not None:
        raise click.UsageError(
            "--plugin-dir and --group-metadata are mutually exclusive"
        )

    target = str(group_metadata or plugin_dir)
    transport_stdout, opened_stdout = _resolve_protocol_stdout(protocol_stdout)
    if group_metadata is not None:
        entrypoint = run_plugin_worker(
            group_metadata=group_metadata,
            stdout=transport_stdout,
        )
    else:
        entrypoint = run_plugin_worker(
            plugin_dir=plugin_dir,
            stdout=transport_stdout,
        )
    try:
        _run_async_entrypoint(
            entrypoint,
            log_message=f"启动插件工作进程：{target}",
            log_level="debug",
            context={"plugin_dir": plugin_dir},
        )
    finally:
        if opened_stdout is not None:
            opened_stdout.close()


@cli.command("serve-worker")
@click.option("--worker-id", default=None, type=str, help="Stable websocket worker id")
@click.option(
    "--plugin-dir",
    "plugin_dirs",
    multiple=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Plugin directory to serve; repeat to host multiple plugins in one worker",
)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8765, type=int, show_default=True)
@click.option("--path", default="/", show_default=True)
@click.option(
    "--tls-ca-file",
    required=True,
    type=click.Path(file_okay=True, dir_okay=False, exists=True, path_type=Path),
)
@click.option(
    "--tls-cert-file",
    required=True,
    type=click.Path(file_okay=True, dir_okay=False, exists=True, path_type=Path),
)
@click.option(
    "--tls-key-file",
    required=True,
    type=click.Path(file_okay=True, dir_okay=False, exists=True, path_type=Path),
)
def serve_worker(
    worker_id: str | None,
    plugin_dirs: tuple[Path, ...],
    host: str,
    port: int,
    path: str,
    tls_ca_file: Path,
    tls_cert_file: Path,
    tls_key_file: Path,
) -> None:
    """Serve one or more plugins as a standalone websocket worker."""
    _run_websocket_worker_entrypoint(
        worker_id=worker_id,
        plugin_dirs=plugin_dirs,
        host=host,
        port=port,
        path=path,
        tls_ca_file=tls_ca_file,
        tls_cert_file=tls_cert_file,
        tls_key_file=tls_key_file,
    )


@cli.command(hidden=True)
@click.option("--worker-id", default=None, type=str)
@click.option(
    "--plugin-dir",
    "plugin_dirs",
    multiple=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8765, type=int, show_default=True)
@click.option("--path", default="/", show_default=True)
@click.option(
    "--tls-ca-file",
    required=True,
    type=click.Path(file_okay=True, dir_okay=False, exists=True, path_type=Path),
)
@click.option(
    "--tls-cert-file",
    required=True,
    type=click.Path(file_okay=True, dir_okay=False, exists=True, path_type=Path),
)
@click.option(
    "--tls-key-file",
    required=True,
    type=click.Path(file_okay=True, dir_okay=False, exists=True, path_type=Path),
)
def websocket(
    worker_id: str | None,
    plugin_dirs: tuple[Path, ...],
    host: str,
    port: int,
    path: str,
    tls_ca_file: Path,
    tls_cert_file: Path,
    tls_key_file: Path,
) -> None:
    """Deprecated websocket runtime wrapper for standalone worker scenarios."""
    logger.warning("'astr websocket' is deprecated; use 'astr serve-worker' instead")
    _run_websocket_worker_entrypoint(
        worker_id=worker_id,
        plugin_dirs=plugin_dirs,
        host=host,
        port=port,
        path=path,
        tls_ca_file=tls_ca_file,
        tls_cert_file=tls_cert_file,
        tls_key_file=tls_key_file,
    )
