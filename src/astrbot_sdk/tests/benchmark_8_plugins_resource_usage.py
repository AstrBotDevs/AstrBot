from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None

from astrbot_sdk.api.star.context import Context
from astrbot_sdk.runtime.galaxy import Galaxy

PLUGIN_COUNT = 8
TARGET_PYTHON = "3.12"
HANDSHAKE_TIMEOUT_SECONDS = 60.0


class BenchmarkContext(Context):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate 8 Python 3.12 plugins and measure resource usage for the "
            "independent worker runtime."
        )
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable used to launch the supervisor process.",
    )
    parser.add_argument(
        "--plugins-dir",
        type=Path,
        default=None,
        help="Optional directory to write generated plugins into.",
    )
    parser.add_argument(
        "--keep-plugins-dir",
        action="store_true",
        help="Keep the generated plugins directory instead of deleting it.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write the benchmark report JSON.",
    )
    return parser.parse_args()


def write_plugin(plugins_dir: Path, index: int) -> None:
    plugin_name = f"plugin_{index:03d}"
    command_name = f"bench_{index:03d}"
    plugin_dir = plugins_dir / plugin_name
    commands_dir = plugin_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / "__init__.py").write_text("", encoding="utf-8")

    manifest = {
        "_schema_version": 2,
        "name": plugin_name,
        "display_name": plugin_name,
        "desc": f"Resource benchmark plugin {index}",
        "author": "codex",
        "version": "0.1.0",
        "runtime": {"python": TARGET_PYTHON},
        "components": [
            {
                "class": f"commands.plugin_{index:03d}:BenchmarkCommand{index:03d}",
                "type": "command",
                "name": command_name,
                "description": command_name,
            }
        ],
    }
    (plugin_dir / "plugin.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")

    module_source = f"""
from astrbot_sdk.api.components.command import CommandComponent
from astrbot_sdk.api.event import AstrMessageEvent, filter
from astrbot_sdk.api.star.context import Context


class BenchmarkCommand{index:03d}(CommandComponent):
    def __init__(self, context: Context):
        self.context = context

    @filter.command("{command_name}")
    async def handle(self, event: AstrMessageEvent):
        yield event.plain_result("{plugin_name}:{command_name}")
""".strip()
    (commands_dir / f"plugin_{index:03d}.py").write_text(
        module_source + "\n",
        encoding="utf-8",
    )


def _collect_with_psutil(root_pid: int) -> dict[str, Any]:
    assert psutil is not None
    root_process = psutil.Process(root_pid)
    processes = [root_process] + root_process.children(recursive=True)
    entries: list[dict[str, Any]] = []
    total_rss = 0

    for process in processes:
        try:
            rss = process.memory_info().rss
            total_rss += rss
            entries.append(
                {
                    "pid": process.pid,
                    "name": process.name(),
                    "rss_mb": round(rss / 1024 / 1024, 2),
                    "cmdline": process.cmdline(),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    entries.sort(key=lambda item: item["pid"])
    return {
        "collector": "psutil",
        "process_count": len(entries),
        "total_rss_mb": round(total_rss / 1024 / 1024, 2),
        "processes": entries,
    }


def _collect_with_ps(root_pid: int) -> dict[str, Any]:
    process = subprocess.run(
        ["ps", "-axo", "pid,ppid,rss,comm"],
        capture_output=True,
        text=True,
        check=True,
    )
    children_by_parent: dict[int, list[tuple[int, int, str]]] = {}
    rss_by_pid: dict[int, int] = {}

    for line in process.stdout.splitlines()[1:]:
        parts = line.strip().split(None, 3)
        if len(parts) != 4:
            continue
        pid, ppid, rss_kb, command = parts
        pid_int = int(pid)
        ppid_int = int(ppid)
        rss_int = int(rss_kb)
        rss_by_pid[pid_int] = rss_int
        children_by_parent.setdefault(ppid_int, []).append((pid_int, rss_int, command))

    queue = [root_pid]
    seen: set[int] = set()
    entries: list[dict[str, Any]] = []
    total_rss = 0

    while queue:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        rss_kb = rss_by_pid.get(pid)
        command = None
        for siblings in children_by_parent.values():
            for child_pid, child_rss, child_command in siblings:
                if child_pid == pid:
                    rss_kb = child_rss
                    command = child_command
                    break
            if command is not None:
                break
        if rss_kb is not None:
            total_rss += rss_kb * 1024
            entries.append(
                {
                    "pid": pid,
                    "name": command or "unknown",
                    "rss_mb": round((rss_kb * 1024) / 1024 / 1024, 2),
                    "cmdline": [command] if command else [],
                }
            )
        for child_pid, _child_rss, _child_command in children_by_parent.get(pid, []):
            queue.append(child_pid)

    entries.sort(key=lambda item: item["pid"])
    return {
        "collector": "ps",
        "process_count": len(entries),
        "total_rss_mb": round(total_rss / 1024 / 1024, 2),
        "processes": entries,
    }


def collect_process_tree_metrics(root_pid: int) -> dict[str, Any]:
    if psutil is not None:
        try:
            return _collect_with_psutil(root_pid)
        except (PermissionError, psutil.Error):
            pass
    return _collect_with_ps(root_pid)


async def terminate_process(process: Any) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        await asyncio.to_thread(process.wait, 10.0)
    except Exception:
        process.kill()
        await asyncio.to_thread(process.wait, 10.0)


async def run_benchmark(plugins_dir: Path, python_executable: str) -> dict[str, Any]:
    for index in range(PLUGIN_COUNT):
        write_plugin(plugins_dir, index)

    galaxy = Galaxy()
    context = BenchmarkContext()
    started_at = time.perf_counter()
    star = await galaxy.connect_to_stdio_star(
        context=context,
        star_name="resource-benchmark",
        config={
            "plugins_dir": str(plugins_dir),
            "python_executable": python_executable,
        },
    )
    connected_at = time.perf_counter()

    client_process = getattr(star._client, "_process", None)
    metadata: dict[str, Any] = {}
    handshake_error: str | None = None
    try:
        metadata = await asyncio.wait_for(
            star.handshake(),
            timeout=HANDSHAKE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        handshake_error = f"{exc.__class__.__name__}: {exc}"

    measured_at = time.perf_counter()
    metrics = (
        collect_process_tree_metrics(client_process.pid) if client_process else {}
    )
    loaded_plugins = sorted(
        metadata_item.name
        for metadata_item in metadata.values()
        if getattr(metadata_item, "name", None)
    )

    stop_error: str | None = None
    try:
        await star.stop()
    except Exception as exc:
        stop_error = f"{exc.__class__.__name__}: {exc}"
        await terminate_process(client_process)

    return {
        "plugin_count": PLUGIN_COUNT,
        "target_python": TARGET_PYTHON,
        "python_executable": python_executable,
        "loaded_plugin_count": len(loaded_plugins),
        "loaded_plugins": loaded_plugins,
        "connect_duration_ms": round((connected_at - started_at) * 1000, 2),
        "handshake_duration_ms": round((measured_at - connected_at) * 1000, 2),
        "startup_total_duration_ms": round((measured_at - started_at) * 1000, 2),
        "handshake_error": handshake_error,
        "metrics": metrics,
        "stop_error": stop_error,
    }


def main() -> None:
    args = parse_args()

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    plugins_dir = args.plugins_dir
    if plugins_dir is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="astrbot-8-plugin-bench-")
        plugins_dir = Path(temp_dir.name)
    else:
        plugins_dir.mkdir(parents=True, exist_ok=True)

    try:
        report = asyncio.run(
            run_benchmark(
                plugins_dir=plugins_dir,
                python_executable=args.python_executable,
            )
        )
    finally:
        if temp_dir is not None and not args.keep_plugins_dir:
            temp_dir.cleanup()

    report["plugins_dir"] = str(plugins_dir)

    if args.output_json is not None:
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
