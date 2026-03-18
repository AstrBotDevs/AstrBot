"""v4 runtime 的插件共享环境规划模块。

这个模块负责“多个插件，共享较少数量 Python 环境”的策略。核心约束是：

- 插件仍然独立发现、独立加载
- Worker 进程仍然保持一插件一进程
- 只有在依赖兼容时才共享 Python 环境

整体流程如下：

1. 先按插件声明的 `runtime.python` 分桶
2. 再按依赖兼容性构建候选分组
3. 为每个分组在 `.astrbot/` 下落地 source、lock、metadata 和 venv 路径
4. 在 worker 启动前准备或同步该分组的共享环境

当前阶段优先保证兼容性，因此仍保留 `--system-site-packages`，也不改变
现有插件 manifest 语义。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .loader import PluginSpec

GROUP_STATE_FILE_NAME = ".group-venv-state.json"

_EXACT_PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")
_NORMALIZE_PATTERN = re.compile(r"[-_.]+")
_PYVENV_VERSION_PATTERN = re.compile(
    r"^(?:version|version_info)\s*=\s*(\d+\.\d+)(?:\.\d+)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _require_uv_binary(uv_binary: str | None) -> str:
    if not uv_binary:
        raise RuntimeError("uv executable not found")
    return uv_binary


def _venv_python_path(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _normalize_package_name(name: str) -> str:
    return _NORMALIZE_PATTERN.sub("-", name).lower()


def _read_pyvenv_major_minor(pyvenv_cfg: Path) -> str | None:
    if not pyvenv_cfg.exists():
        return None
    try:
        content = pyvenv_cfg.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _PYVENV_VERSION_PATTERN.search(content)
    if match is None:
        return None
    return match.group(1)


def _requirement_lines(plugin: PluginSpec) -> list[str]:
    if not plugin.requirements_path.exists():
        return []

    lines: list[str] = []
    for raw_line in plugin.requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


@dataclass(slots=True)
class EnvironmentGroup:
    """一个或多个兼容插件最终共享的环境描述。

    分组是环境复用的最小单位。`plugins` 中的所有插件都会使用同一个
    `python_path`、lockfile 和 venv 目录，但运行时仍然各自启动独立的
    worker 进程。
    """

    id: str
    python_version: str
    plugins: list[PluginSpec]
    source_path: Path
    lockfile_path: Path
    metadata_path: Path
    venv_path: Path
    python_path: Path
    environment_fingerprint: str


@dataclass(slots=True)
class EnvironmentPlanResult:
    """一次完整规划得到的结果。

    `plugins` 只包含成功完成规划的插件。
    `skipped_plugins` 记录规划失败的插件及原因，这类插件即使单独成组也没
    有得到可用的共享环境。
    """

    groups: list[EnvironmentGroup] = field(default_factory=list)
    plugins: list[PluginSpec] = field(default_factory=list)
    plugin_to_group: dict[str, EnvironmentGroup] = field(default_factory=dict)
    skipped_plugins: dict[str, str] = field(default_factory=dict)


class EnvironmentPlanner:
    """负责共享环境规划和分组工件落地。

    对 supervisor 启动来说，这个类主要回答两个问题：

    - 哪些插件可以共享一个环境
    - 这个共享环境应该对应哪份 lockfile 和哪个 venv 路径

    它本身不负责真正创建或同步 venv，这部分在规划结束后交给
    `GroupEnvironmentManager` 处理。
    """

    def __init__(self, repo_root: Path, uv_binary: str | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.uv_binary = uv_binary or shutil.which("uv")
        self.cache_dir = self.repo_root / ".uv-cache"
        self.artifacts_dir = self.repo_root / ".astrbot"
        self.group_dir = self.artifacts_dir / "groups"
        self.lock_dir = self.artifacts_dir / "locks"
        self.env_dir = self.artifacts_dir / "envs"
        self._compatibility_cache: dict[str, bool] = {}

    def plan(self, plugins: list[PluginSpec]) -> EnvironmentPlanResult:
        """为当前插件集合生成稳定的共享环境规划。

        之所以在 worker 启动前完成规划，是为了让 supervisor 能够：

        - 只跳过依赖无法满足的那部分插件
        - 在兼容插件之间复用同一个环境
        - 清理旧规划遗留的 `.astrbot` 工件
        """
        if not plugins:
            self.cleanup_artifacts([])
            return EnvironmentPlanResult()
        _require_uv_binary(self.uv_binary)

        candidate_groups = self._build_candidate_groups(plugins)
        planned_groups: list[EnvironmentGroup] = []
        skipped_plugins: dict[str, str] = {}
        for group_plugins in candidate_groups:
            materialized, skipped = self._materialize_candidate_group(group_plugins)
            planned_groups.extend(materialized)
            skipped_plugins.update(skipped)

        planned_groups.sort(key=lambda group: (group.python_version, group.id))
        self.cleanup_artifacts(planned_groups)

        plugin_to_group = {
            plugin.name: group for group in planned_groups for plugin in group.plugins
        }
        planned_plugins = [
            plugin for plugin in plugins if plugin.name in plugin_to_group
        ]
        return EnvironmentPlanResult(
            groups=planned_groups,
            plugins=planned_plugins,
            plugin_to_group=plugin_to_group,
            skipped_plugins=skipped_plugins,
        )

    def _build_candidate_groups(
        self, plugins: list[PluginSpec]
    ) -> list[list[PluginSpec]]:
        """用贪心方式把插件装入兼容性候选组。

        分组过程保持确定性，规则是：

        - Python 版本是第一层硬边界
        - `requirements.txt` 约束更多的插件优先落位
        - 若仍相同，则按插件名排序
        """
        buckets: dict[str, list[PluginSpec]] = {}
        for plugin in plugins:
            buckets.setdefault(plugin.python_version, []).append(plugin)

        planned_groups: list[list[PluginSpec]] = []
        for python_version in sorted(buckets):
            python_groups: list[list[PluginSpec]] = []
            for plugin in self._sort_plugins(buckets[python_version]):
                placed = False
                for group_plugins in python_groups:
                    if self._is_compatible([*group_plugins, plugin]):
                        group_plugins.append(plugin)
                        placed = True
                        break
                if not placed:
                    python_groups.append([plugin])
            planned_groups.extend(python_groups)
        return planned_groups

    @staticmethod
    def _sort_plugins(plugins: list[PluginSpec]) -> list[PluginSpec]:
        return sorted(
            plugins,
            key=lambda plugin: (-len(_requirement_lines(plugin)), plugin.name),
        )

    def _is_compatible(self, plugins: list[PluginSpec]) -> bool:
        """判断一组插件是否可以共享一个环境。

        兼容性判断先走一个便宜的快速路径：

        - 如果每条 requirement 都是 `pkg==1.2.3` 这种精确版本锁定
        - 且归一化后的包名之间没有解析出冲突版本
        - 那么无需调用求解器，直接认为这一组兼容

        更复杂的情况则回退到 `uv pip compile`，以它的求解结果作为最终依
        赖兼容性的判断依据。
        """
        cache_key = self._compatibility_cache_key(plugins)
        cached = self._compatibility_cache.get(cache_key)
        if cached is not None:
            return cached

        requirement_lines = self._collect_requirement_lines(plugins)
        if not requirement_lines:
            self._compatibility_cache[cache_key] = True
            return True

        if self._merge_exact_requirements(requirement_lines) is not None:
            self._compatibility_cache[cache_key] = True
            return True

        with tempfile.TemporaryDirectory(
            prefix="astrbot-env-plan-",
            dir=self.repo_root,
        ) as temp_dir:
            source_path = Path(temp_dir) / "compat.in"
            output_path = Path(temp_dir) / "compat.txt"
            self._write_source_file(source_path, plugins)
            try:
                self._compile_lockfile(
                    source_path=source_path,
                    output_path=output_path,
                    python_version=plugins[0].python_version,
                )
            except RuntimeError:
                self._compatibility_cache[cache_key] = False
                return False

        self._compatibility_cache[cache_key] = True
        return True

    def _materialize_candidate_group(
        self,
        plugins: list[PluginSpec],
    ) -> tuple[list[EnvironmentGroup], dict[str, str]]:
        """为一个候选组创建工件，失败时自动拆分。

        如果整组插件无法生成 lockfile，规划器会退回到“一插件一组”继续尝
        试，避免单个坏插件阻塞整批插件启动。
        """
        try:
            return [self._materialize_group(plugins)], {}
        except RuntimeError as exc:
            if len(plugins) == 1:
                return [], {plugins[0].name: str(exc)}

            materialized: list[EnvironmentGroup] = []
            skipped: dict[str, str] = {}
            for plugin in plugins:
                groups, child_skipped = self._materialize_candidate_group([plugin])
                materialized.extend(groups)
                skipped.update(child_skipped)
            return materialized, skipped

    def _materialize_group(self, plugins: list[PluginSpec]) -> EnvironmentGroup:
        """落地定义一个共享环境所需的全部文件。

        分组身份由 Python 版本和插件集合共同决定。
        环境指纹则会进一步包含编译后的 lockfile 内容，这样当依赖解析结果
        变化时，已有环境就可以走增量同步而不是盲目重建。
        """
        group_id = self._group_identity(plugins)[:16]
        python_version = plugins[0].python_version
        source_path = self.group_dir / f"{group_id}.in"
        lockfile_path = self.lock_dir / f"{group_id}.txt"
        metadata_path = self.group_dir / f"{group_id}.json"
        venv_path = self.env_dir / group_id
        python_path = _venv_python_path(venv_path)

        source_path.parent.mkdir(parents=True, exist_ok=True)
        lockfile_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        venv_path.parent.mkdir(parents=True, exist_ok=True)

        self._write_source_file(source_path, plugins)
        self._write_lockfile(
            lockfile_path=lockfile_path,
            source_path=source_path,
            plugins=plugins,
            python_version=python_version,
        )
        environment_fingerprint = self._environment_fingerprint(
            plugins=plugins,
            python_version=python_version,
            lockfile_path=lockfile_path,
        )
        metadata_path.write_text(
            json.dumps(
                {
                    "group_id": group_id,
                    "python_version": python_version,
                    "plugins": [plugin.name for plugin in plugins],
                    "plugin_entries": [
                        {
                            "name": plugin.name,
                            "plugin_dir": str(plugin.plugin_dir),
                        }
                        for plugin in plugins
                    ],
                    "source_path": str(source_path),
                    "lockfile_path": str(lockfile_path),
                    "venv_path": str(venv_path),
                    "environment_fingerprint": environment_fingerprint,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        return EnvironmentGroup(
            id=group_id,
            python_version=python_version,
            plugins=list(plugins),
            source_path=source_path,
            lockfile_path=lockfile_path,
            metadata_path=metadata_path,
            venv_path=venv_path,
            python_path=python_path,
            environment_fingerprint=environment_fingerprint,
        )

    def _write_source_file(self, source_path: Path, plugins: list[PluginSpec]) -> None:
        """写入供 lockfile 生成使用的分组 requirements 输入文件。"""
        lines: list[str] = []
        for plugin in sorted(plugins, key=lambda item: item.name):
            requirements = _requirement_lines(plugin)
            if not requirements:
                continue
            lines.append(f"# {plugin.name}")
            lines.extend(requirements)
            lines.append("")

        content = "\n".join(lines).rstrip()
        if content:
            content += "\n"
        source_path.write_text(content, encoding="utf-8")

    def _write_lockfile(
        self,
        *,
        lockfile_path: Path,
        source_path: Path,
        plugins: list[PluginSpec],
        python_version: str,
    ) -> None:
        """为一个分组生成 lockfile。

        即使依赖集合为空，也会故意生成空 lockfile，这样整个共享环境流水
        线的处理方式可以保持一致。
        """
        if not self._collect_requirement_lines(plugins):
            lockfile_path.write_text("", encoding="utf-8")
            return

        self._compile_lockfile(
            source_path=source_path,
            output_path=lockfile_path,
            python_version=python_version,
        )

    def _compile_lockfile(
        self,
        *,
        source_path: Path,
        output_path: Path,
        python_version: str,
    ) -> None:
        """把依赖求解委托给 `uv pip compile`。"""
        uv_binary = _require_uv_binary(self.uv_binary)
        self._run_command(
            [
                uv_binary,
                "pip",
                "compile",
                "--python-version",
                python_version,
                "--no-managed-python",
                "--no-python-downloads",
                "--quiet",
                str(source_path),
                "-o",
                str(output_path),
            ],
            cwd=self.repo_root,
            command_name=f"compile lockfile for {source_path.name}",
        )

    def _run_command(self, command: list[str], *, cwd: Path, command_name: str) -> None:
        process = subprocess.run(
            command,
            cwd=str(cwd),
            env={**os.environ, "UV_CACHE_DIR": str(self.cache_dir)},
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(
                f"{command_name} failed with exit code {process.returncode}: "
                f"{process.stderr.strip() or process.stdout.strip()}"
            )

    def cleanup_artifacts(self, groups: list[EnvironmentGroup]) -> None:
        """清理不再被当前规划引用的 `.astrbot` 工件。

        清理范围只覆盖规划器自己维护的共享环境工件，不会碰旧式插件目录下
        的本地 `.venv`。
        """
        active_group_ids = {group.id for group in groups}
        self._cleanup_group_artifacts(active_group_ids)
        self._cleanup_lockfiles(active_group_ids)
        self._cleanup_envs(active_group_ids)

    def _cleanup_group_artifacts(self, active_group_ids: set[str]) -> None:
        if not self.group_dir.exists():
            return
        for entry in self.group_dir.iterdir():
            if entry.suffix not in {".in", ".json"}:
                continue
            if entry.stem in active_group_ids:
                continue
            entry.unlink(missing_ok=True)

    def _cleanup_lockfiles(self, active_group_ids: set[str]) -> None:
        if not self.lock_dir.exists():
            return
        for entry in self.lock_dir.iterdir():
            if entry.suffix != ".txt":
                continue
            if entry.stem in active_group_ids:
                continue
            entry.unlink(missing_ok=True)

    def _cleanup_envs(self, active_group_ids: set[str]) -> None:
        if not self.env_dir.exists():
            return
        for entry in self.env_dir.iterdir():
            if entry.name in active_group_ids:
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)

    def _compatibility_cache_key(self, plugins: list[PluginSpec]) -> str:
        payload = {
            "python_version": plugins[0].python_version if plugins else "",
            "plugins": [
                {
                    "name": plugin.name,
                    "requirements": _requirement_lines(plugin),
                }
                for plugin in sorted(plugins, key=lambda item: item.name)
            ],
        }
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _group_identity(plugins: list[PluginSpec]) -> str:
        payload = {
            "python_version": plugins[0].python_version if plugins else "",
            "plugins": sorted(plugin.name for plugin in plugins),
        }
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _environment_fingerprint(
        *,
        plugins: list[PluginSpec],
        python_version: str,
        lockfile_path: Path,
    ) -> str:
        payload = {
            "python_version": python_version,
            "plugins": sorted(plugin.name for plugin in plugins),
            "lockfile": lockfile_path.read_text(encoding="utf-8"),
        }
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _collect_requirement_lines(plugins: list[PluginSpec]) -> list[str]:
        lines: list[str] = []
        for plugin in plugins:
            lines.extend(_requirement_lines(plugin))
        return lines

    @staticmethod
    def _merge_exact_requirements(requirement_lines: list[str]) -> list[str] | None:
        merged: dict[str, str] = {}
        for line in requirement_lines:
            match = _EXACT_PIN_PATTERN.fullmatch(line)
            if match is None:
                return None
            package_name = _normalize_package_name(match.group(1))
            existing = merged.get(package_name)
            if existing is not None and existing != line:
                return None
            merged[package_name] = line
        return [merged[name] for name in sorted(merged)]


class GroupEnvironmentManager:
    """负责创建、校验和同步一个已经规划好的共享环境。"""

    def __init__(self, repo_root: Path, uv_binary: str | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.uv_binary = uv_binary or shutil.which("uv")
        self.cache_dir = self.repo_root / ".uv-cache"

    def prepare(self, group: EnvironmentGroup) -> Path:
        """确保分组对应的解释器路径已经可以用于 worker 启动。

        行为概括如下：

        - 环境缺失、Python 版本不对、lockfile 丢失：重建
        - 环境结构还在但指纹变化：执行 `uv pip sync`
        - 否则：直接复用现有解释器路径
        """
        _require_uv_binary(self.uv_binary)

        state_path = group.venv_path / GROUP_STATE_FILE_NAME
        state = self._load_state(state_path)
        if (
            not group.python_path.exists()
            or not self._matches_python_version(group.venv_path, group.python_version)
            or not group.lockfile_path.exists()
        ):
            self._rebuild(group)
            self._write_state(state_path, group)
        elif not self._state_matches_group(state, group):
            self._sync_existing(group)
            self._write_state(state_path, group)
        return group.python_path

    def _rebuild(self, group: EnvironmentGroup) -> None:
        if group.venv_path.exists():
            shutil.rmtree(group.venv_path)
        self._create_venv(group)
        self._sync_lockfile(group)

    def _sync_existing(self, group: EnvironmentGroup) -> None:
        self._sync_lockfile(group)

    def _sync_lockfile(self, group: EnvironmentGroup) -> None:
        """让已安装包与该分组的 lockfile 精确对齐。"""
        uv_binary = _require_uv_binary(self.uv_binary)
        self._run_command(
            [
                uv_binary,
                "pip",
                "sync",
                "--python",
                str(group.python_path),
                "--allow-empty-requirements",
                str(group.lockfile_path),
            ],
            cwd=self.repo_root,
            command_name=f"sync group env {group.id}",
        )

    def _create_venv(self, group: EnvironmentGroup) -> None:
        """为一个分组创建共享 venv。

        当前迁移阶段仍保留 `--system-site-packages`，以兼容那些仍然隐式依
        赖宿主环境包的旧插件。
        """
        uv_binary = _require_uv_binary(self.uv_binary)
        self._run_command(
            [
                uv_binary,
                "venv",
                "--python",
                group.python_version,
                "--system-site-packages",
                "--no-python-downloads",
                "--no-managed-python",
                str(group.venv_path),
            ],
            cwd=self.repo_root,
            command_name=f"create group venv {group.id}",
        )

    def _run_command(self, command: list[str], *, cwd: Path, command_name: str) -> None:
        process = subprocess.run(
            command,
            cwd=str(cwd),
            env={**os.environ, "UV_CACHE_DIR": str(self.cache_dir)},
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(
                f"{command_name} failed with exit code {process.returncode}: "
                f"{process.stderr.strip() or process.stdout.strip()}"
            )

    @staticmethod
    def _matches_python_version(venv_path: Path, version: str) -> bool:
        return _read_pyvenv_major_minor(venv_path / "pyvenv.cfg") == version

    @staticmethod
    def _load_state(state_path: Path) -> dict[str, object]:
        if not state_path.exists():
            return {}
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _write_state(state_path: Path, group: EnvironmentGroup) -> None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "group_id": group.id,
                    "python_version": group.python_version,
                    "environment_fingerprint": group.environment_fingerprint,
                    "plugins": [plugin.name for plugin in group.plugins],
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _state_matches_group(state: dict[str, object], group: EnvironmentGroup) -> bool:
        return (
            state.get("group_id") == group.id
            and state.get("python_version") == group.python_version
            and state.get("environment_fingerprint") == group.environment_fingerprint
        )
