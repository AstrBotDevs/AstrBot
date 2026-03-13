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
    1. 对插件集合做共享环境规划
    2. 按 Python 版本和依赖兼容性构建环境分组
    3. 为每个分组生成 lock/source/metadata 工件
    4. 必要时重建或同步分组虚拟环境
    5. 将单个插件映射到所属分组环境

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
        - PluginEnvironmentManager 管理分组共享环境
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
import inspect
import json
import os
import re
import sys
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

from .._legacy_loader import (
    build_legacy_manifest,
    load_legacy_main_component_classes,
    load_plugin_manifest_payload,
    looks_like_legacy_plugin,
    resolve_plugin_component_classes,
)
from .._legacy_runtime import (
    LegacyRuntimeAdapter,
    build_capability_legacy_runtime,
    build_handler_legacy_runtime,
    create_legacy_component_context,
    finalize_legacy_component_instance,
    is_new_star_component,
    plan_legacy_component_construction,
)
from ..api.basic.astrbot_config import AstrBotConfig
from ..decorators import get_capability_meta, get_handler_meta
from ..protocol.descriptors import CapabilityDescriptor, HandlerDescriptor
from .environment_groups import (
    EnvironmentGroup,
    EnvironmentPlanResult,
    EnvironmentPlanner,
    GroupEnvironmentManager,
)

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
    plugin_id: str = ""
    legacy_context: Any | None = None
    compat_filters: list[Any] = field(default_factory=list)
    legacy_runtime: LegacyRuntimeAdapter | None = field(
        init=False, default=None, repr=False
    )

    def __post_init__(self) -> None:
        if self.legacy_context is None:
            return
        self.legacy_runtime = build_handler_legacy_runtime(
            self.legacy_context,
            self.callable,
            compat_filters=self.compat_filters or None,
        )
        self.compat_filters = list(self.legacy_runtime.filters)


@dataclass(slots=True)
class LoadedCapability:
    descriptor: CapabilityDescriptor
    callable: Any
    owner: Any
    plugin_id: str = ""
    legacy_context: Any | None = None
    legacy_runtime: LegacyRuntimeAdapter | None = field(
        init=False, default=None, repr=False
    )

    def __post_init__(self) -> None:
        if self.legacy_context is None:
            return
        self.legacy_runtime = build_capability_legacy_runtime(self.legacy_context)


@dataclass(slots=True)
class LoadedPlugin:
    plugin: PluginSpec
    handlers: list[LoadedHandler]
    capabilities: list[LoadedCapability] = field(default_factory=list)
    instances: list[Any] = field(default_factory=list)


def _is_new_star_component(component_cls: Any) -> bool:
    return is_new_star_component(component_cls)


def _create_legacy_context(component_cls: Any, plugin_name: str) -> Any:
    return create_legacy_component_context(component_cls, plugin_name)


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
    return looks_like_legacy_plugin(plugin_dir)


def _build_legacy_manifest(plugin_dir: Path) -> tuple[Path, dict[str, Any]]:
    return build_legacy_manifest(
        plugin_dir,
        read_yaml=_read_yaml,
        default_python_version=_default_python_version(),
        manifest_flag_key=LEGACY_MAIN_MANIFEST_KEY,
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
    return load_legacy_main_component_classes(
        plugin_name=plugin.name,
        plugin_dir=plugin.plugin_dir,
    )


def _plugin_component_classes(plugin: PluginSpec) -> list[type[Any]]:
    return resolve_plugin_component_classes(
        plugin_name=plugin.name,
        plugin_dir=plugin.plugin_dir,
        manifest_data=plugin.manifest_data,
        manifest_flag_key=LEGACY_MAIN_MANIFEST_KEY,
        import_string=import_string,
    )


def load_plugin_spec(plugin_dir: Path) -> PluginSpec:
    plugin_dir = plugin_dir.resolve()
    requirements_path = plugin_dir / "requirements.txt"
    manifest_path, manifest_data = load_plugin_manifest_payload(
        plugin_dir,
        read_yaml=_read_yaml,
        default_python_version=_default_python_version(),
        manifest_flag_key=LEGACY_MAIN_MANIFEST_KEY,
    )
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


def validate_plugin_spec(plugin: PluginSpec) -> None:
    """校验单个插件规范，供 CLI 和发现流程复用。"""
    manifest_data = plugin.manifest_data
    is_legacy_main = bool(manifest_data.get(LEGACY_MAIN_MANIFEST_KEY))

    if not is_legacy_main and not plugin.requirements_path.exists():
        raise ValueError("missing requirements.txt")

    raw_name = manifest_data.get("name")
    if not is_legacy_main and (not isinstance(raw_name, str) or not raw_name):
        raise ValueError("plugin name is required")

    raw_runtime = manifest_data.get("runtime") or {}
    raw_python = raw_runtime.get("python")
    if not is_legacy_main and (not isinstance(raw_python, str) or not raw_python):
        raise ValueError("runtime.python is required")

    components = manifest_data.get("components")
    if not isinstance(components, list):
        raise ValueError("components must be a list")

    if is_legacy_main:
        return

    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise ValueError(f"components[{index}] must be an object")
        class_path = component.get("class")
        if not isinstance(class_path, str) or ":" not in class_path:
            raise ValueError(f"components[{index}].class must be '<module>:<Class>'")


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
        if not manifest_path.exists() and not _looks_like_legacy_plugin(entry):
            continue
        plugin: PluginSpec | None = None
        try:
            plugin = load_plugin_spec(entry)
            validate_plugin_spec(plugin)
        except Exception as exc:
            skip_key = entry.name
            if plugin is not None:
                raw_name = plugin.manifest_data.get("name")
                if (
                    isinstance(raw_name, str)
                    and raw_name
                    and str(exc) != "missing requirements.txt"
                ):
                    skip_key = raw_name
            skipped_plugins[skip_key] = f"failed to parse plugin manifest: {exc}"
            continue
        plugin_name = plugin.name
        if not isinstance(plugin_name, str) or not plugin_name:
            skipped_plugins[entry.name] = "plugin name is required"
            continue
        if plugin_name in seen_names:
            skipped_plugins[plugin_name] = "duplicate plugin name"
            continue
        seen_names.add(plugin_name)
        plugins.append(plugin)
    return PluginDiscoveryResult(plugins=plugins, skipped_plugins=skipped_plugins)


class PluginEnvironmentManager:
    """运行时访问分组环境管理的门面层。

    运行时仍然保留历史上的 `prepare_environment(plugin)` 调用入口，但底层
    实现已经变成两阶段模型：

    1. `plan()` 负责解析跨插件分组和共享工件
    2. `prepare_environment()` 负责把单个插件映射到它所属的分组环境
    """

    def __init__(self, repo_root: Path, uv_binary: str | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.uv_binary = uv_binary
        self.cache_dir = self.repo_root / ".uv-cache"
        self._planner = EnvironmentPlanner(self.repo_root, uv_binary=uv_binary)
        self._group_manager = GroupEnvironmentManager(
            self.repo_root, uv_binary=uv_binary
        )
        self.uv_binary = self._planner.uv_binary
        self._plan_result: EnvironmentPlanResult | None = None

    def plan(self, plugins: list[PluginSpec]) -> EnvironmentPlanResult:
        """为当前插件集合生成共享环境规划。"""
        plan_result = self._planner.plan(plugins)
        self._plan_result = plan_result
        return plan_result

    def prepare_group_environment(self, group: EnvironmentGroup) -> Path:
        """返回指定分组的解释器路径。"""
        if self._plan_result is None:
            self._plan_result = EnvironmentPlanResult(groups=[group])
        return self._group_manager.prepare(group)

    def prepare_environment(self, plugin: PluginSpec) -> Path:
        """返回该插件所属分组环境的解释器路径。

        如果调用方还没有先对整批插件做规划，这里会自动创建一个至少包含当
        前插件的最小规划，以保证旧的“单插件直接调用”模式仍然可用。
        """
        if (
            self._plan_result is None
            or plugin.name not in self._plan_result.plugin_to_group
        ):
            planned_plugins = (
                list(self._plan_result.plugins) if self._plan_result else []
            )
            if plugin.name not in {item.name for item in planned_plugins}:
                planned_plugins.append(plugin)
            self.plan(planned_plugins)

        assert self._plan_result is not None
        group = self._plan_result.plugin_to_group.get(plugin.name)
        if group is None:
            reason = self._plan_result.skipped_plugins.get(plugin.name)
            if reason is not None:
                raise RuntimeError(reason)
            raise RuntimeError(f"environment plan missing plugin: {plugin.name}")

        return self.prepare_group_environment(group)

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
        try:
            content = pyvenv_cfg.read_text(encoding="utf-8")
        except OSError:
            return False
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
            construction = plan_legacy_component_construction(
                component_cls,
                plugin_name=plugin.name,
                shared_legacy_context=shared_legacy_context,
                plugin_config=plugin_config,
                default_config_factory=lambda: AstrBotConfig(
                    {},
                    save_path=_plugin_config_path(plugin.plugin_dir, plugin.name),
                ),
            )
            shared_legacy_context = construction.shared_legacy_context
            legacy_context = construction.legacy_context
            instance = component_cls(*construction.constructor_args)
            finalize_legacy_component_instance(
                instance,
                legacy_context=legacy_context,
                component_config=construction.component_config,
            )
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
                        plugin_id=plugin.name,
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
                    plugin_id=plugin.name,
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
