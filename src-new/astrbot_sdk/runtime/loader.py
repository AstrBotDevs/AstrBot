from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

from ..decorators import get_handler_meta
from ..protocol.descriptors import HandlerDescriptor
from ..star import Star

STATE_FILE_NAME = ".astrbot-worker-state.json"


def _venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


@dataclass(slots=True)
class PluginSpec:
    name: str
    plugin_dir: Path
    manifest_path: Path
    requirements_path: Path
    python_version: str
    manifest_data: dict[str, Any]


@dataclass(slots=True)
class PluginDiscoveryResult:
    plugins: list[PluginSpec]
    skipped_plugins: dict[str, str]


@dataclass(slots=True)
class LoadedHandler:
    descriptor: HandlerDescriptor
    callable: Any
    owner: Any
    legacy_context: Any | None = None


@dataclass(slots=True)
class LoadedPlugin:
    plugin: PluginSpec
    handlers: list[LoadedHandler]
    instances: list[Any]


def _is_new_star_component(component_cls: Any) -> bool:
    if not isinstance(component_cls, type) or not issubclass(component_cls, Star):
        return False
    marker = getattr(component_cls, "__astrbot_is_new_star__", None)
    if callable(marker):
        return bool(marker())
    return True


def _create_legacy_context(component_cls: Any, plugin_name: str) -> Any:
    factory = getattr(component_cls, "_astrbot_create_legacy_context", None)
    if callable(factory):
        return factory(plugin_name)
    from ..api.star.context import Context as LegacyContext

    return LegacyContext(plugin_name)


def _iter_handler_names(instance: Any) -> list[str]:
    handler_names = getattr(instance.__class__, "__handlers__", ())
    if handler_names:
        return list(handler_names)
    return list(dir(instance))


def load_plugin_spec(plugin_dir: Path) -> PluginSpec:
    plugin_dir = plugin_dir.resolve()
    manifest_path = plugin_dir / "plugin.yaml"
    requirements_path = plugin_dir / "requirements.txt"
    manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    runtime = manifest_data.get("runtime") or {}
    python_version = (
        runtime.get("python") or f"{sys.version_info.major}.{sys.version_info.minor}"
    )
    return PluginSpec(
        name=str(manifest_data.get("name") or plugin_dir.name),
        plugin_dir=plugin_dir,
        manifest_path=manifest_path,
        requirements_path=requirements_path,
        python_version=str(python_version),
        manifest_data=manifest_data,
    )


def discover_plugins(plugins_dir: Path) -> PluginDiscoveryResult:
    plugins_root = plugins_dir.resolve()
    skipped_plugins: dict[str, str] = {}
    plugins: list[PluginSpec] = []
    seen_names: set[str] = set()

    if not plugins_root.exists():
        return PluginDiscoveryResult([], {})

    for entry in sorted(plugins_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        manifest_path = entry / "plugin.yaml"
        requirements_path = entry / "requirements.txt"
        if not manifest_path.exists():
            continue
        if not requirements_path.exists():
            skipped_plugins[entry.name] = "missing requirements.txt"
            continue
        try:
            manifest_data = (
                yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            )
        except Exception as exc:
            skipped_plugins[entry.name] = f"failed to parse plugin.yaml: {exc}"
            continue
        plugin_name = manifest_data.get("name")
        runtime = manifest_data.get("runtime") or {}
        python_version = runtime.get("python")
        components = manifest_data.get("components")
        if not isinstance(plugin_name, str) or not plugin_name:
            skipped_plugins[entry.name] = "plugin name is required"
            continue
        if plugin_name in seen_names:
            skipped_plugins[plugin_name] = "duplicate plugin name"
            continue
        if not isinstance(components, list) or not components:
            skipped_plugins[plugin_name] = "components must be a non-empty list"
            continue
        if not isinstance(python_version, str) or not python_version:
            skipped_plugins[plugin_name] = "runtime.python is required"
            continue
        seen_names.add(plugin_name)
        plugins.append(
            PluginSpec(
                name=plugin_name,
                plugin_dir=entry.resolve(),
                manifest_path=manifest_path.resolve(),
                requirements_path=requirements_path.resolve(),
                python_version=python_version,
                manifest_data=manifest_data,
            )
        )
    return PluginDiscoveryResult(plugins=plugins, skipped_plugins=skipped_plugins)


class PluginEnvironmentManager:
    def __init__(self, repo_root: Path, uv_binary: str | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.uv_binary = uv_binary or shutil.which("uv")
        self.cache_dir = self.repo_root / ".uv-cache"

    def prepare_environment(self, plugin: PluginSpec) -> Path:
        if not self.uv_binary:
            raise RuntimeError("uv executable not found")
        state_path = plugin.plugin_dir / STATE_FILE_NAME
        venv_dir = plugin.plugin_dir / ".venv"
        python_path = _venv_python_path(venv_dir)
        fingerprint = self._fingerprint(plugin)
        state = self._load_state(state_path)
        if (
            not python_path.exists()
            or not self._matches_python_version(venv_dir, plugin.python_version)
            or state.get("fingerprint") != fingerprint
        ):
            self._rebuild(plugin, venv_dir, python_path)
            self._write_state(state_path, plugin, fingerprint)
        return python_path

    def _rebuild(self, plugin: PluginSpec, venv_dir: Path, python_path: Path) -> None:
        if venv_dir.exists():
            shutil.rmtree(venv_dir)
        self._run_command(
            [
                self.uv_binary,
                "venv",
                "--python",
                plugin.python_version,
                "--system-site-packages",
                "--no-python-downloads",
                "--no-managed-python",
                str(venv_dir),
            ],
            cwd=self.repo_root,
            command_name=f"create venv for {plugin.name}",
        )
        requirements_text = plugin.requirements_path.read_text(encoding="utf-8").strip()
        if not requirements_text:
            return
        self._run_command(
            [
                self.uv_binary,
                "pip",
                "install",
                "--python",
                str(python_path),
                "-r",
                str(plugin.requirements_path),
            ],
            cwd=plugin.plugin_dir,
            command_name=f"install requirements for {plugin.name}",
        )

    def _run_command(
        self,
        command: list[str],
        *,
        cwd: Path,
        command_name: str,
    ) -> None:
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
    def _fingerprint(plugin: PluginSpec) -> str:
        requirements = plugin.requirements_path.read_text(encoding="utf-8")
        payload = {
            "python_version": plugin.python_version,
            "requirements": requirements,
        }
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)

    @staticmethod
    def _load_state(state_path: Path) -> dict[str, Any]:
        if not state_path.exists():
            return {}
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _write_state(state_path: Path, plugin: PluginSpec, fingerprint: str) -> None:
        state_path.write_text(
            json.dumps(
                {
                    "plugin": plugin.name,
                    "python_version": plugin.python_version,
                    "fingerprint": fingerprint,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _matches_python_version(venv_dir: Path, version: str) -> bool:
        pyvenv_cfg = venv_dir / "pyvenv.cfg"
        if not pyvenv_cfg.exists():
            return False
        content = pyvenv_cfg.read_text(encoding="utf-8")
        match = re.search(r"version\s*=\s*(\d+\.\d+)\.\d+", content, re.IGNORECASE)
        return match is not None and match.group(1) == version


def load_plugin(plugin: PluginSpec) -> LoadedPlugin:
    plugin_path = str(plugin.plugin_dir)
    if plugin_path not in sys.path:
        sys.path.insert(0, plugin_path)

    instances: list[Any] = []
    handlers: list[LoadedHandler] = []
    for component in plugin.manifest_data.get("components", []):
        class_path = component.get("class")
        if not isinstance(class_path, str) or ":" not in class_path:
            continue
        component_cls = import_string(class_path)
        legacy_context = None
        if _is_new_star_component(component_cls):
            instance = component_cls()
        else:
            legacy_context = _create_legacy_context(component_cls, plugin.name)
            try:
                instance = component_cls(legacy_context)
            except TypeError:
                instance = component_cls()
                if getattr(instance, "context", None) is None:
                    setattr(instance, "context", legacy_context)
        instances.append(instance)
        for name in _iter_handler_names(instance):
            bound = getattr(instance, name)
            func = getattr(bound, "__func__", bound)
            meta = get_handler_meta(func)
            if meta is None or meta.trigger is None:
                continue
            handler_id = f"{plugin.name}:{instance.__class__.__module__}.{instance.__class__.__name__}.{name}"
            handlers.append(
                LoadedHandler(
                    descriptor=HandlerDescriptor(
                        id=handler_id,
                        trigger=meta.trigger,
                        priority=meta.priority,
                        permissions=meta.permissions.model_copy(deep=True),
                    ),
                    callable=bound,
                    owner=instance,
                    legacy_context=legacy_context,
                )
            )
    return LoadedPlugin(plugin=plugin, handlers=handlers, instances=instances)


def import_string(path: str) -> Any:
    module_name, attr = path.split(":", 1)
    module = import_module(module_name)
    return getattr(module, attr)
