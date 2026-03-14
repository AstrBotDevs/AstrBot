"""legacy 插件发现与 main.py 包装导入辅助。"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import re
import sys
import types
from pathlib import Path
from typing import Any

from .star import Star

PLUGIN_MANIFEST_FILE = "plugin.yaml"
LEGACY_METADATA_FILE = "metadata.yaml"
LEGACY_MAIN_FILE = "main.py"


def looks_like_legacy_plugin(plugin_dir: Path) -> bool:
    return (
        not (plugin_dir / PLUGIN_MANIFEST_FILE).exists()
        and (plugin_dir / LEGACY_MAIN_FILE).exists()
    )


def build_legacy_manifest(
    plugin_dir: Path,
    *,
    read_yaml,
    default_python_version: str,
    manifest_flag_key: str,
) -> tuple[Path, dict[str, Any]]:
    metadata_path = plugin_dir / LEGACY_METADATA_FILE
    metadata = read_yaml(metadata_path) if metadata_path.exists() else {}
    plugin_name = str(metadata.get("name") or plugin_dir.name)
    manifest_data: dict[str, Any] = {
        "name": plugin_name,
        "author": metadata.get("author"),
        "desc": metadata.get("desc") or metadata.get("description"),
        "version": metadata.get("version"),
        "repo": metadata.get("repo"),
        "display_name": metadata.get("display_name"),
        "runtime": {"python": default_python_version},
        "components": [],
        manifest_flag_key: True,
    }
    return (
        metadata_path if metadata_path.exists() else plugin_dir / LEGACY_MAIN_FILE,
        manifest_data,
    )


def load_plugin_manifest_payload(
    plugin_dir: Path,
    *,
    read_yaml,
    default_python_version: str,
    manifest_flag_key: str,
) -> tuple[Path, dict[str, Any]]:
    manifest_path = plugin_dir / PLUGIN_MANIFEST_FILE
    if manifest_path.exists():
        return manifest_path, read_yaml(manifest_path)
    return build_legacy_manifest(
        plugin_dir,
        read_yaml=read_yaml,
        default_python_version=default_python_version,
        manifest_flag_key=manifest_flag_key,
    )


def legacy_package_name(plugin_name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", plugin_name)
    return f"_astrbot_legacy_pkg_{sanitized}"


def _prepare_legacy_package(package_name: str, plugin_dir: Path) -> None:
    package = types.ModuleType(package_name)
    package.__path__ = [str(plugin_dir)]
    package.__package__ = package_name
    sys.modules[package_name] = package
    sys.modules.pop(f"{package_name}.main", None)
    importlib.invalidate_caches()


def _iter_main_module_component_classes(module: types.ModuleType) -> list[type[Any]]:
    component_classes: list[type[Any]] = []
    for candidate in module.__dict__.values():
        if not inspect.isclass(candidate):
            continue
        if candidate.__module__ != module.__name__:
            continue
        if not issubclass(candidate, Star) or candidate is Star:
            continue
        component_classes.append(candidate)
    return component_classes


def load_legacy_main_component_classes(
    *,
    plugin_name: str,
    plugin_dir: Path,
) -> list[type[Any]]:
    package_name = legacy_package_name(plugin_name)
    module_name = f"{package_name}.main"
    module_path = plugin_dir / LEGACY_MAIN_FILE
    _prepare_legacy_package(package_name, plugin_dir)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return _iter_main_module_component_classes(module)


def resolve_plugin_component_classes(
    *,
    plugin_name: str,
    plugin_dir: Path,
    manifest_data: dict[str, Any],
    manifest_flag_key: str,
    import_string,
) -> list[type[Any]]:
    component_classes: list[type[Any]] = []
    for component in manifest_data.get("components", []):
        class_path = component.get("class")
        if not isinstance(class_path, str) or ":" not in class_path:
            continue
        component_classes.append(import_string(class_path, plugin_dir=plugin_dir))
    if component_classes:
        return component_classes
    if manifest_data.get(manifest_flag_key):
        return load_legacy_main_component_classes(
            plugin_name=plugin_name,
            plugin_dir=plugin_dir,
        )
    return []
