"""插件加载模块。

定义插件发现、环境管理和加载的核心逻辑。
支持新旧两种 Star 组件的兼容加载。

核心概念：
    PluginSpec: 插件规范，描述插件的基本信息
    PluginDiscoveryResult: 插件发现结果，包含成功和跳过的插件
    PluginEnvironmentManager: 插件虚拟环境管理器
    LoadedHandler: 加载后的处理器，包含描述符和可调用对象
    LoadedPlugin: 加载后的插件，包含处理器和实例

插件发现流程：
    1. 扫描 plugins_dir 下的子目录
    2. 检查 plugin.yaml 和 requirements.txt
    3. 解析 manifest_data 获取插件信息
    4. 验证必要字段（name, components, runtime.python）
    5. 返回 PluginDiscoveryResult

环境管理流程：
    1. 检查 .venv 目录是否存在
    2. 检查 Python 版本是否匹配
    3. 检查指纹是否变化（requirements 内容）
    4. 必要时重建虚拟环境
    5. 使用 uv 安装依赖

插件加载流程：
    1. 将插件目录添加到 sys.path
    2. 遍历 components 列表
    3. 动态导入组件类
    4. 判断是否为新版 Star
    5. 创建实例（新版直接实例化，旧版传入 legacy_context）
    6. 扫描处理器方法
    7. 构建 HandlerDescriptor

新旧 Star 组件兼容：
    新版 Star:
        - 继承自 Star 基类
        - __astrbot_is_new_star__ 返回 True
        - 无参构造函数
        - 通过 @handler 装饰器注册处理器

    旧版 Star:
        - 不继承或 __astrbot_is_new_star__ 返回 False
        - 需要 legacy_context 参数
        - 通过 @xxx_handler 装饰器注册处理器
        - 使用 extras_configs 传递配置

与旧版对比：
    旧版 StarManager:
        - 通过 plugin.yaml 发现插件
        - 动态导入组件类并实例化
        - 注册到 star_handlers_registry
        - 使用 functools.partial 绑定实例
        - 无环境管理
        - 无指纹缓存

    新版 loader.py:
        - PluginSpec 描述插件规范
        - PluginEnvironmentManager 管理虚拟环境
        - load_plugin() 加载并解析组件
        - LoadedHandler 封装处理器和描述符
        - 支持新旧 Star 组件兼容
        - 支持环境指纹缓存

plugin.yaml 格式：
    name: my_plugin
    author: author_name
    desc: Plugin description
    version: 1.0.0
    runtime:
        python: "3.11"
    components:
        - class: my_plugin.main:MyComponent

`loader` 是 runtime 与插件代码之间的边界层，负责三件事：

- 从 `plugin.yaml` 解析出可运行的 `PluginSpec`
- 用 `uv` 为插件准备独立环境
- 把组件实例和 handler 元数据整理成 `LoadedPlugin`

legacy 兼容也集中放在这里，尤其是“同一插件共享一个 `LegacyContext`”这一旧语义。
"""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import inspect
import os
import re
import shutil
import subprocess
import sys
import types
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

from ..api.basic import AstrBotConfig
from ..decorators import get_capability_meta, get_handler_meta
from ..protocol.descriptors import CapabilityDescriptor, HandlerDescriptor
from ..star import Star

STATE_FILE_NAME = ".astrbot-worker-state.json"
PLUGIN_MANIFEST_FILE = "plugin.yaml"
LEGACY_METADATA_FILE = "metadata.yaml"
LEGACY_MAIN_FILE = "main.py"
CONFIG_SCHEMA_FILE = "_conf_schema.json"
LEGACY_MAIN_MANIFEST_KEY = "__legacy_main__"
PLUGIN_METADATA_ATTR = "__astrbot_plugin_metadata__"


def _default_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


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
class LoadedCapability:
    descriptor: CapabilityDescriptor
    callable: Any
    owner: Any
    legacy_context: Any | None = None


@dataclass(slots=True)
class LoadedPlugin:
    plugin: PluginSpec
    handlers: list[LoadedHandler]
    capabilities: list[LoadedCapability] = field(default_factory=list)
    instances: list[Any] = field(default_factory=list)


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


def _iter_discoverable_names(instance: Any) -> list[str]:
    handler_names = list(dict.fromkeys(_iter_handler_names(instance)))
    known_names = set(handler_names)
    extra_names = sorted(name for name in dir(instance) if name not in known_names)
    return [*handler_names, *extra_names]


def _resolve_handler_candidate(instance: Any, name: str) -> tuple[Any, Any] | None:
    """解析 handler 名称，避免在扫描阶段触发无关 descriptor 副作用。"""
    try:
        raw = inspect.getattr_static(instance, name)
    except AttributeError:
        return None

    candidates = [raw]
    wrapped = getattr(raw, "__func__", None)
    if wrapped is not None:
        candidates.append(wrapped)

    for candidate in candidates:
        meta = get_handler_meta(candidate)
        if meta is not None and meta.trigger is not None:
            return getattr(instance, name), meta
    return None


def _resolve_capability_candidate(instance: Any, name: str) -> tuple[Any, Any] | None:
    try:
        raw = inspect.getattr_static(instance, name)
    except AttributeError:
        return None

    candidates = [raw]
    wrapped = getattr(raw, "__func__", None)
    if wrapped is not None:
        candidates.append(wrapped)

    for candidate in candidates:
        meta = get_capability_meta(candidate)
        if meta is not None:
            return getattr(instance, name), meta
    return None


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _read_requirements_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _looks_like_legacy_plugin(plugin_dir: Path) -> bool:
    return (
        not (plugin_dir / PLUGIN_MANIFEST_FILE).exists()
        and (plugin_dir / LEGACY_MAIN_FILE).exists()
    )


def _build_legacy_manifest(plugin_dir: Path) -> tuple[Path, dict[str, Any]]:
    metadata_path = plugin_dir / LEGACY_METADATA_FILE
    metadata = _read_yaml(metadata_path) if metadata_path.exists() else {}
    plugin_name = str(metadata.get("name") or plugin_dir.name)
    manifest_data: dict[str, Any] = {
        "name": plugin_name,
        "author": metadata.get("author"),
        "desc": metadata.get("desc") or metadata.get("description"),
        "version": metadata.get("version"),
        "repo": metadata.get("repo"),
        "display_name": metadata.get("display_name"),
        "runtime": {"python": _default_python_version()},
        "components": [],
        LEGACY_MAIN_MANIFEST_KEY: True,
    }
    return (
        metadata_path if metadata_path.exists() else plugin_dir / LEGACY_MAIN_FILE,
        manifest_data,
    )


def _plugin_config_dir(plugin_dir: Path) -> Path:
    if plugin_dir.parent.name == "plugins" and plugin_dir.parent.parent.exists():
        return plugin_dir.parent.parent / "config"
    return plugin_dir / "data" / "config"


def _plugin_config_path(plugin_dir: Path, plugin_name: str) -> Path:
    return _plugin_config_dir(plugin_dir) / f"{plugin_name}_config.json"


def _schema_default(field_schema: dict[str, Any]) -> Any:
    if "default" in field_schema:
        return copy.deepcopy(field_schema["default"])

    field_type = str(field_schema.get("type") or "string")
    if field_type == "object":
        items = field_schema.get("items")
        if isinstance(items, dict):
            return {
                key: _normalize_config_value(child_schema, None)
                for key, child_schema in items.items()
                if isinstance(child_schema, dict)
            }
        return {}
    if field_type in {"list", "template_list", "file"}:
        return []
    if field_type == "dict":
        return {}
    if field_type == "int":
        return 0
    if field_type == "float":
        return 0.0
    if field_type == "bool":
        return False
    return ""


def _normalize_config_value(field_schema: dict[str, Any], value: Any) -> Any:
    field_type = str(field_schema.get("type") or "string")
    default_value = _schema_default(field_schema)

    if field_type == "object":
        items = field_schema.get("items")
        if not isinstance(items, dict):
            return default_value
        current = value if isinstance(value, dict) else {}
        return {
            key: _normalize_config_value(child_schema, current.get(key))
            for key, child_schema in items.items()
            if isinstance(child_schema, dict)
        }
    if field_type in {"list", "template_list", "file"}:
        return copy.deepcopy(value) if isinstance(value, list) else default_value
    if field_type == "dict":
        return copy.deepcopy(value) if isinstance(value, dict) else default_value
    if field_type == "int":
        return (
            value
            if isinstance(value, int) and not isinstance(value, bool)
            else default_value
        )
    if field_type == "float":
        return (
            value
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else default_value
        )
    if field_type == "bool":
        return value if isinstance(value, bool) else default_value
    if field_type in {"string", "text"}:
        return value if isinstance(value, str) else default_value
    return copy.deepcopy(value) if value is not None else default_value


def _load_plugin_config(plugin: PluginSpec) -> AstrBotConfig | None:
    schema_path = plugin.plugin_dir / CONFIG_SCHEMA_FILE
    if not schema_path.exists():
        return None

    try:
        schema_payload = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception:
        schema_payload = {}
    schema = schema_payload if isinstance(schema_payload, dict) else {}

    config_path = _plugin_config_path(plugin.plugin_dir, plugin.name)
    try:
        existing_payload = (
            json.loads(config_path.read_text(encoding="utf-8"))
            if config_path.exists()
            else {}
        )
    except Exception:
        existing_payload = {}
    existing = existing_payload if isinstance(existing_payload, dict) else {}
    normalized = {
        key: _normalize_config_value(field_schema, existing.get(key))
        for key, field_schema in schema.items()
        if isinstance(field_schema, dict)
    }
    config = AstrBotConfig(normalized, save_path=config_path)
    if not config_path.exists() or normalized != existing:
        config.save_config()
    return config


def _legacy_component_classes(plugin: PluginSpec) -> list[type[Any]]:
    package_name = _legacy_package_name(plugin)
    module_name = f"{package_name}.main"
    module_path = plugin.plugin_dir / LEGACY_MAIN_FILE
    _prepare_legacy_package(package_name, plugin.plugin_dir)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    component_classes: list[type[Any]] = []
    for _, candidate in inspect.getmembers(module, inspect.isclass):
        if candidate.__module__ != module.__name__:
            continue
        if not issubclass(candidate, Star) or candidate is Star:
            continue
        component_classes.append(candidate)

    component_classes.sort(key=lambda cls: cls.__name__)
    return component_classes


def _plugin_component_classes(plugin: PluginSpec) -> list[type[Any]]:
    component_classes: list[type[Any]] = []
    for component in plugin.manifest_data.get("components", []):
        class_path = component.get("class")
        if not isinstance(class_path, str) or ":" not in class_path:
            continue
        component_classes.append(
            import_string(class_path, plugin_dir=plugin.plugin_dir)
        )

    if component_classes:
        return component_classes
    if plugin.manifest_data.get(LEGACY_MAIN_MANIFEST_KEY):
        return _legacy_component_classes(plugin)
    return []


def _select_legacy_constructor_args(
    component_cls: type[Any],
    legacy_context: Any,
    config: AstrBotConfig | None,
) -> tuple[Any, ...]:
    try:
        signature = inspect.signature(component_cls)
    except (TypeError, ValueError):
        return (legacy_context, config) if config is not None else (legacy_context,)

    positional_params = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    has_varargs = any(
        parameter.kind == inspect.Parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )
    max_args = None if has_varargs else len(positional_params)

    if config is not None and (max_args is None or max_args >= 2):
        return (legacy_context, config)
    if max_args is None or max_args >= 1:
        return (legacy_context,)
    return ()


def _legacy_constructor_accepts_config(component_cls: type[Any]) -> bool:
    try:
        signature = inspect.signature(component_cls)
    except (TypeError, ValueError):
        return True

    positional_params = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    has_varargs = any(
        parameter.kind == inspect.Parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )
    return has_varargs or len(positional_params) >= 2


def load_plugin_spec(plugin_dir: Path) -> PluginSpec:
    plugin_dir = plugin_dir.resolve()
    manifest_path = plugin_dir / PLUGIN_MANIFEST_FILE
    requirements_path = plugin_dir / "requirements.txt"
    if manifest_path.exists():
        manifest_data = _read_yaml(manifest_path)
    else:
        manifest_path, manifest_data = _build_legacy_manifest(plugin_dir)
    runtime = manifest_data.get("runtime") or {}
    python_version = runtime.get("python") or _default_python_version()
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
        manifest_path = entry / PLUGIN_MANIFEST_FILE
        requirements_path = entry / "requirements.txt"
        if not manifest_path.exists() and not _looks_like_legacy_plugin(entry):
            continue
        if manifest_path.exists() and not requirements_path.exists():
            skipped_plugins[entry.name] = "missing requirements.txt"
            continue
        try:
            if manifest_path.exists():
                manifest_data = _read_yaml(manifest_path)
            else:
                manifest_path, manifest_data = _build_legacy_manifest(entry)
        except Exception as exc:
            skipped_plugins[entry.name] = f"failed to parse plugin manifest: {exc}"
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
        if not isinstance(components, list):
            skipped_plugins[plugin_name] = "components must be a list"
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
        requirements_text = _read_requirements_text(plugin.requirements_path).strip()
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
        requirements = _read_requirements_text(plugin.requirements_path)
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
    capabilities: list[LoadedCapability] = []
    shared_legacy_context = None
    plugin_config = _load_plugin_config(plugin)
    for component_cls in _plugin_component_classes(plugin):
        legacy_context = None
        if _is_new_star_component(component_cls):
            instance = component_cls()
        else:
            if shared_legacy_context is None:
                # 旧版 StarManager 为同一插件复用一个 Context 实例。
                shared_legacy_context = _create_legacy_context(
                    component_cls, plugin.name
                )
            legacy_context = shared_legacy_context
            component_config = plugin_config
            if component_config is None and _legacy_constructor_accepts_config(
                component_cls
            ):
                component_config = AstrBotConfig(
                    {},
                    save_path=_plugin_config_path(plugin.plugin_dir, plugin.name),
                )
            constructor_args = _select_legacy_constructor_args(
                component_cls, legacy_context, component_config
            )
            instance = component_cls(*constructor_args)
            if getattr(instance, "context", None) is None:
                setattr(instance, "context", legacy_context)
            if (
                component_config is not None
                and getattr(instance, "config", None) is None
            ):
                setattr(instance, "config", component_config)
        instances.append(instance)
        for name in _iter_discoverable_names(instance):
            resolved = _resolve_handler_candidate(instance, name)
            if resolved is None:
                capability = _resolve_capability_candidate(instance, name)
                if capability is None:
                    continue
                bound, meta = capability
                capabilities.append(
                    LoadedCapability(
                        descriptor=meta.descriptor.model_copy(deep=True),
                        callable=bound,
                        owner=instance,
                        legacy_context=legacy_context,
                    )
                )
                continue
            bound, meta = resolved
            handler_id = f"{plugin.name}:{instance.__class__.__module__}.{instance.__class__.__name__}.{name}"
            handlers.append(
                LoadedHandler(
                    descriptor=HandlerDescriptor(
                        id=handler_id,
                        trigger=meta.trigger,
                        kind=str(meta.kind),
                        contract=meta.contract,
                        priority=meta.priority,
                        permissions=meta.permissions.model_copy(deep=True),
                    ),
                    callable=bound,
                    owner=instance,
                    legacy_context=legacy_context,
                )
            )
    return LoadedPlugin(
        plugin=plugin,
        handlers=handlers,
        capabilities=capabilities,
        instances=instances,
    )


def _path_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _plugin_defines_module_root(plugin_dir: Path, root_name: str) -> bool:
    return (plugin_dir / f"{root_name}.py").exists() or (
        plugin_dir / root_name
    ).exists()


def _module_belongs_to_plugin(module: Any, plugin_dir: Path) -> bool:
    file_path = getattr(module, "__file__", None)
    if isinstance(file_path, str) and _path_within_root(Path(file_path), plugin_dir):
        return True

    package_paths = getattr(module, "__path__", None)
    if package_paths is None:
        return False
    return any(
        isinstance(candidate, str) and _path_within_root(Path(candidate), plugin_dir)
        for candidate in package_paths
    )


def _purge_module_root(root_name: str) -> None:
    for module_name in list(sys.modules):
        if module_name == root_name or module_name.startswith(f"{root_name}."):
            sys.modules.pop(module_name, None)


def _legacy_package_name(plugin: PluginSpec) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", plugin.name)
    return f"_astrbot_legacy_pkg_{sanitized}"


def _prepare_legacy_package(package_name: str, plugin_dir: Path) -> None:
    _purge_module_root(package_name)
    package = types.ModuleType(package_name)
    package.__file__ = str(plugin_dir / "__init__.py")
    package.__package__ = package_name
    package.__path__ = [str(plugin_dir)]
    sys.modules[package_name] = package
    importlib.invalidate_caches()


def _prepare_plugin_import(module_name: str, plugin_dir: Path | None) -> None:
    if plugin_dir is None:
        return

    plugin_root = plugin_dir.resolve()
    plugin_path = str(plugin_root)
    if plugin_path not in sys.path:
        sys.path.insert(0, plugin_path)

    root_name = module_name.split(".", 1)[0]
    if not _plugin_defines_module_root(plugin_root, root_name):
        return

    cached_root = sys.modules.get(root_name)
    cached_module = sys.modules.get(module_name)
    if cached_root is not None and not _module_belongs_to_plugin(
        cached_root, plugin_root
    ):
        _purge_module_root(root_name)
    elif cached_module is not None and not _module_belongs_to_plugin(
        cached_module, plugin_root
    ):
        _purge_module_root(root_name)

    importlib.invalidate_caches()


def import_string(path: str, plugin_dir: Path | None = None) -> Any:
    module_name, attr = path.split(":", 1)
    _prepare_plugin_import(module_name, plugin_dir)
    module = import_module(module_name)
    return getattr(module, attr)
