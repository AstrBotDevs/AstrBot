# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_NEW_DIR = PROJECT_ROOT / "src-new"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_NEW_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_NEW_DIR))

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None

from astrbot_sdk.protocol.messages import InitializeOutput, PeerInfo
from astrbot_sdk.runtime.bootstrap import SupervisorRuntime
from astrbot_sdk.runtime.loader import PluginEnvironmentManager
from astrbot_sdk.runtime.peer import Peer

from tests_v4.helpers import make_transport_pair

DEFAULT_MULTIPLIERS = [1, 2, 4, 8, 12]
DEFAULT_CONFLICT_COUNT = 1
DEFAULT_COMPATIBLE_COUNT = 5
SAMPLE_INTERVAL_SECONDS = 0.05
EXACT_PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")


@dataclass(slots=True)
class ProcessTreeSnapshot:
    collector: str
    process_count: int
    total_rss_bytes: int
    total_rss_mb: float


@dataclass(slots=True)
class BenchmarkCaseResult:
    multiplier: int
    conflict_plugins: int
    compatible_plugins: int
    total_plugins: int
    group_count: int
    skipped_plugins: int
    startup_duration_ms: float
    steady_rss_mb: float
    peak_rss_mb: float
    process_count: int
    expected_groups: int


class SyntheticGroupedEnvManager(PluginEnvironmentManager):
    """用于 benchmark 的分组环境管理器。

    这个实现保留真实的 supervisor 启动流程和插件分组规划，但把下面两类成
    本较高、且对本地压力测试不稳定的动作替换掉：

    - `uv pip compile` 改为直接生成可重复的伪 lockfile
    - `uv venv` / `uv pip sync` 改为为每个分组创建一个指向当前解释器的路径

    这样得到的结果更接近“分组规划 + worker 启动”的资源开销，而不是被
    外网索引、包下载或磁盘安装速度主导。
    """

    def __init__(self, repo_root: Path) -> None:
        super().__init__(repo_root, uv_binary="synthetic-uv")
        self._original_is_compatible = self._planner._is_compatible
        self._planner._is_compatible = self._synthetic_is_compatible
        self._planner._compile_lockfile = self._synthetic_compile_lockfile
        self._group_manager.prepare = self._synthetic_prepare_environment

    def _synthetic_is_compatible(self, plugins) -> bool:
        requirement_lines = self._planner._collect_requirement_lines(plugins)
        if not requirement_lines:
            return True

        merged = self._planner._merge_exact_requirements(requirement_lines)
        if merged is not None:
            return True

        if all(EXACT_PIN_PATTERN.fullmatch(line) for line in requirement_lines):
            return False
        return self._original_is_compatible(plugins)

    @staticmethod
    def _synthetic_compile_lockfile(
        *,
        source_path: Path,
        output_path: Path,
        python_version: str,
    ) -> None:
        lines = []
        for raw_line in source_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            lines.append(line)
        output = [f"# synthetic lockfile for python {python_version}"]
        output.extend(sorted(dict.fromkeys(lines)))
        output_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")

    @staticmethod
    def _synthetic_prepare_environment(group) -> Path:
        group.python_path.parent.mkdir(parents=True, exist_ok=True)
        if group.python_path.exists():
            return group.python_path

        target = Path(sys.executable).resolve()
        if os.name == "nt":
            shutil.copy2(target, group.python_path)
            current_mode = group.python_path.stat().st_mode
            group.python_path.chmod(current_mode | stat.S_IEXEC)
        else:
            os.symlink(target, group.python_path)
        return group.python_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark v4 grouped plugin environments with configurable counts "
            "for conflicting and compatible plugins."
        )
    )
    parser.add_argument(
        "--multipliers",
        nargs="+",
        type=int,
        default=DEFAULT_MULTIPLIERS,
        help="Scale factors applied to the base plugin counts.",
    )
    parser.add_argument(
        "--conflict-count",
        type=int,
        default=DEFAULT_CONFLICT_COUNT,
        help="Base count of conflicting plugins before applying multipliers.",
    )
    parser.add_argument(
        "--compatible-count",
        type=int,
        default=DEFAULT_COMPATIBLE_COUNT,
        help="Base count of compatible plugins before applying multipliers.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path for the JSON benchmark report.",
    )
    parser.add_argument(
        "--keep-temp-dir",
        action="store_true",
        help="Keep the generated temporary workspace for inspection.",
    )
    return parser.parse_args()


def write_benchmark_plugin(
    *,
    plugins_dir: Path,
    plugin_name: str,
    command_name: str,
    requirement: str,
) -> None:
    plugin_dir = plugins_dir / plugin_name
    commands_dir = plugin_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / "__init__.py").write_text("", encoding="utf-8")
    (plugin_dir / "requirements.txt").write_text(requirement, encoding="utf-8")
    (plugin_dir / "plugin.yaml").write_text(
        textwrap.dedent(
            f"""\
            _schema_version: 2
            name: {plugin_name}
            display_name: {plugin_name}
            desc: grouped environment benchmark plugin
            author: codex
            version: 0.1.0
            runtime:
              python: "{sys.version_info.major}.{sys.version_info.minor}"
            components:
              - class: commands.main:BenchmarkCommand
                type: command
                name: {command_name}
                description: {command_name}
            """
        ),
        encoding="utf-8",
    )
    (commands_dir / "main.py").write_text(
        textwrap.dedent(
            f"""\
            from astrbot_sdk.api.components.command import CommandComponent
            from astrbot_sdk.api.event import AstrMessageEvent, filter
            from astrbot_sdk.api.star.context import Context


            class BenchmarkCommand(CommandComponent):
                def __init__(self, context: Context):
                    self.context = context

                @filter.command("{command_name}")
                async def handle(self, event: AstrMessageEvent):
                    yield event.plain_result("{plugin_name}:{command_name}")
            """
        ),
        encoding="utf-8",
    )


def create_plugin_matrix(
    *,
    plugins_dir: Path,
    multiplier: int,
    conflict_base_count: int,
    compatible_base_count: int,
) -> tuple[int, int]:
    conflict_count = conflict_base_count * multiplier
    compatible_count = compatible_base_count * multiplier

    for index in range(compatible_count):
        write_benchmark_plugin(
            plugins_dir=plugins_dir,
            plugin_name=f"compatible_{index:03d}",
            command_name=f"compatible_{index:03d}",
            requirement="shared-demo==1.0.0\n",
        )

    for index in range(conflict_count):
        write_benchmark_plugin(
            plugins_dir=plugins_dir,
            plugin_name=f"conflict_{index:03d}",
            command_name=f"conflict_{index:03d}",
            requirement=f"shared-demo==2.0.{index}\n",
        )

    return conflict_count, compatible_count


def _snapshot_with_psutil(root_pid: int) -> ProcessTreeSnapshot:
    assert psutil is not None
    root = psutil.Process(root_pid)
    processes = [root] + root.children(recursive=True)
    total_rss = 0
    seen = 0
    for process in processes:
        try:
            total_rss += process.memory_info().rss
            seen += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return ProcessTreeSnapshot(
        collector="psutil",
        process_count=seen,
        total_rss_bytes=total_rss,
        total_rss_mb=round(total_rss / 1024 / 1024, 2),
    )


def _snapshot_with_ps(root_pid: int) -> ProcessTreeSnapshot:
    result = subprocess.run(
        ["ps", "-axo", "pid,ppid,rss"],
        check=True,
        capture_output=True,
        text=True,
    )
    children_by_parent: dict[int, list[int]] = {}
    rss_by_pid: dict[int, int] = {}
    for line in result.stdout.splitlines()[1:]:
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        pid, ppid, rss_kb = parts
        pid_int = int(pid)
        ppid_int = int(ppid)
        rss_by_pid[pid_int] = int(rss_kb) * 1024
        children_by_parent.setdefault(ppid_int, []).append(pid_int)

    queue = [root_pid]
    seen: set[int] = set()
    total_rss = 0
    while queue:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        total_rss += rss_by_pid.get(pid, 0)
        queue.extend(children_by_parent.get(pid, []))

    return ProcessTreeSnapshot(
        collector="ps",
        process_count=len(seen),
        total_rss_bytes=total_rss,
        total_rss_mb=round(total_rss / 1024 / 1024, 2),
    )


def collect_process_tree_snapshot(root_pid: int) -> ProcessTreeSnapshot:
    if psutil is not None:
        try:
            return _snapshot_with_psutil(root_pid)
        except (PermissionError, psutil.Error):
            pass
    return _snapshot_with_ps(root_pid)


async def sample_peak_rss(root_pid: int, stop_event: asyncio.Event) -> float:
    peak_bytes = 0
    while True:
        snapshot = await asyncio.to_thread(collect_process_tree_snapshot, root_pid)
        peak_bytes = max(peak_bytes, snapshot.total_rss_bytes)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SAMPLE_INTERVAL_SECONDS)
            break
        except asyncio.TimeoutError:
            continue
    return round(peak_bytes / 1024 / 1024, 2)


async def start_core_peer() -> tuple[Peer, Any]:
    left, right = make_transport_pair()
    core = Peer(
        transport=left,
        peer_info=PeerInfo(name="benchmark-core", role="core", version="v4"),
    )
    core.set_initialize_handler(
        lambda _message: asyncio.sleep(
            0,
            result=InitializeOutput(
                peer=PeerInfo(name="benchmark-core", role="core", version="v4"),
                capabilities=[],
                metadata={},
            ),
        )
    )
    await core.start()
    return core, right


async def run_case(
    case_root: Path,
    multiplier: int,
    *,
    conflict_base_count: int,
    compatible_base_count: int,
) -> BenchmarkCaseResult:
    plugins_dir = case_root / "plugins"
    conflict_count, compatible_count = create_plugin_matrix(
        plugins_dir=plugins_dir,
        multiplier=multiplier,
        conflict_base_count=conflict_base_count,
        compatible_base_count=compatible_base_count,
    )
    env_manager = SyntheticGroupedEnvManager(case_root)
    core, supervisor_transport = await start_core_peer()
    runtime = SupervisorRuntime(
        transport=supervisor_transport,
        plugins_dir=plugins_dir,
        env_manager=env_manager,
    )

    peak_stop_event = asyncio.Event()
    peak_task = asyncio.create_task(sample_peak_rss(os.getpid(), peak_stop_event))
    started_at = time.perf_counter()
    try:
        await runtime.start()
        await core.wait_until_remote_initialized()
        startup_duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        plan_result = env_manager._plan_result
        if plan_result is None:
            raise RuntimeError("benchmark plan result missing after runtime start")

        steady_snapshot = await asyncio.to_thread(
            collect_process_tree_snapshot, os.getpid()
        )
        peak_rss_mb = max(
            steady_snapshot.total_rss_mb,
            await _finish_peak_sampler(peak_stop_event, peak_task),
        )
        expected_groups = conflict_count + (1 if compatible_count else 0)
        return BenchmarkCaseResult(
            multiplier=multiplier,
            conflict_plugins=conflict_count,
            compatible_plugins=compatible_count,
            total_plugins=conflict_count + compatible_count,
            group_count=len(plan_result.groups),
            skipped_plugins=len(runtime.skipped_plugins),
            startup_duration_ms=startup_duration_ms,
            steady_rss_mb=steady_snapshot.total_rss_mb,
            peak_rss_mb=peak_rss_mb,
            process_count=steady_snapshot.process_count,
            expected_groups=expected_groups,
        )
    finally:
        peak_stop_event.set()
        with contextlib.suppress(Exception):
            await peak_task
        await stop_runtime_concurrently(runtime, core)


async def _finish_peak_sampler(
    stop_event: asyncio.Event, peak_task: asyncio.Task[float]
) -> float:
    stop_event.set()
    return await peak_task


async def stop_runtime_concurrently(runtime: SupervisorRuntime, core: Peer) -> None:
    session_stops = [
        session.stop() for session in list(runtime.worker_sessions.values())
    ]
    if session_stops:
        await asyncio.gather(*session_stops, return_exceptions=True)
    await runtime.peer.stop()
    await core.stop()


def render_table(results: list[BenchmarkCaseResult]) -> str:
    headers = [
        "倍数",
        "冲突",
        "兼容",
        "总插件",
        "分组",
        "预期分组",
        "启动(ms)",
        "稳态RSS(MB)",
        "峰值RSS(MB)",
        "进程数",
    ]
    rows = [
        [
            str(item.multiplier),
            str(item.conflict_plugins),
            str(item.compatible_plugins),
            str(item.total_plugins),
            str(item.group_count),
            str(item.expected_groups),
            f"{item.startup_duration_ms:.2f}",
            f"{item.steady_rss_mb:.2f}",
            f"{item.peak_rss_mb:.2f}",
            str(item.process_count),
        ]
        for item in results
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    lines = [
        "  ".join(headers[index].ljust(widths[index]) for index in range(len(headers))),
        "  ".join("-" * widths[index] for index in range(len(headers))),
    ]
    lines.extend(
        "  ".join(row[index].ljust(widths[index]) for index in range(len(headers)))
        for row in rows
    )
    return "\n".join(lines)


async def run_benchmark(args: argparse.Namespace) -> list[BenchmarkCaseResult]:
    temp_dir_context: Any
    if args.keep_temp_dir:
        workspace_root = PROJECT_ROOT / ".tmp-benchmark-grouped-env"
        workspace_root.mkdir(parents=True, exist_ok=True)
        temp_dir_context = contextlib.nullcontext(str(workspace_root))
    else:
        temp_dir_context = tempfile.TemporaryDirectory(prefix="astrbot-grouped-bench-")

    results: list[BenchmarkCaseResult] = []
    with temp_dir_context as temp_dir:
        workspace_root = Path(temp_dir)
        for multiplier in args.multipliers:
            case_root = workspace_root / f"case_{multiplier:02d}"
            if case_root.exists():
                shutil.rmtree(case_root)
            case_root.mkdir(parents=True, exist_ok=True)
            results.append(
                await run_case(
                    case_root,
                    multiplier,
                    conflict_base_count=args.conflict_count,
                    compatible_base_count=args.compatible_count,
                )
            )
    return results


def write_json_report(
    *,
    output_path: Path,
    conflict_base_count: int,
    compatible_base_count: int,
    results: list[BenchmarkCaseResult],
) -> None:
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_ratio": {
            "conflict_plugins": conflict_base_count,
            "compatible_plugins": compatible_base_count,
        },
        "multipliers": [item.multiplier for item in results],
        "results": [asdict(item) for item in results],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


async def async_main() -> int:
    args = parse_args()
    if args.conflict_count < 0 or args.compatible_count < 0:
        raise SystemExit("conflict-count 和 compatible-count 不能为负数")
    if any(multiplier <= 0 for multiplier in args.multipliers):
        raise SystemExit("multipliers 必须全部大于 0")
    results = await run_benchmark(args)
    print(render_table(results))
    if args.output_json is not None:
        write_json_report(
            output_path=args.output_json,
            conflict_base_count=args.conflict_count,
            compatible_base_count=args.compatible_count,
            results=results,
        )
        print(f"\nJSON 报告已写入: {args.output_json}")

    mismatched = [
        item
        for item in results
        if item.group_count != item.expected_groups or item.skipped_plugins != 0
    ]
    return 1 if mismatched else 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
