"""插件加载模块。

定义插件发现、环境管理和加载的核心逻辑。
仅支持 astrbot-sdk 新版 Star 组件。

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
    4. 直接实例化（无参构造函数）
    5. 扫描处理器方法
    6. 构建 HandlerDescriptor

plugin.yaml 格式：
    name: my_plugin
    author: author_name
    repo: my_plugin
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
"""

from __future__ import annotations

import builtins
import contextlib
import copy
import hashlib
import importlib
import importlib.abc
import inspect
import json
import os
import re
import shutil
import sys
import threading
import types
import typing
from dataclasses import dataclass, field, replace
from importlib import import_module
from pathlib import Path
from collections.abc import Sequence
from importlib.machinery import ModuleSpec, PathFinder
from typing import Any, Literal, TypeAlias, TypeVar, cast

import yaml

from .._internal.command_model import resolve_command_model_param
from .._internal.injected_params import is_framework_injected_parameter
from .._internal.invocation_context import caller_plugin_scope, current_caller_plugin_id
from .._internal.plugin_ids import (
    capability_belongs_to_plugin,
    plugin_capability_prefix,
    validate_plugin_id,
)
from .._internal.sdk_logger import logger
from .._internal.typing_utils import unwrap_optional
from ..decorators import (
    ConversationMeta,
    LimiterMeta,
    get_agent_meta,
    get_capability_meta,
    get_handler_meta,
    get_llm_tool_meta,
)
from ..llm.agents import AgentSpec
from ..llm.entities import LLMToolSpec
from ..protocol.descriptors import (
    CapabilityDescriptor,
    HandlerDescriptor,
    ParamSpec,
    ScheduleTrigger,
)
from ..types import GreedyStr
from .environment_groups import (
    EnvironmentGroup,
    EnvironmentPlanner,
    EnvironmentPlanResult,
    GroupEnvironmentManager,
)

PLUGIN_MANIFEST_FILE = "plugin.yaml"
STATE_FILE_NAME = ".astrbot-worker-state.json"
CONFIG_SCHEMA_FILE = "_conf_schema.json"
PLUGIN_METADATA_ATTR = "__astrbot_plugin_metadata__"
ParamTypeName: TypeAlias = Literal[
    "str", "int", "float", "bool", "optional", "greedy_str"
]
OptionalInnerType: TypeAlias = Literal["str", "int", "float", "bool"] | None
HandlerKind: TypeAlias = Literal["handler", "hook", "tool", "session"]
DiscoverySeverity: TypeAlias = Literal["warning", "error"]
DiscoveryPhase: TypeAlias = Literal["discovery", "load", "lifecycle", "reload"]
_PLUGIN_IMPORT_LOCK = threading.RLock()
_VALID_HANDLER_KINDS: tuple[HandlerKind, ...] = ("handler", "hook", "tool", "session")
_PLUGIN_PACKAGE_PREFIX = "astrbot_ext_"
_GITHUB_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_GITHUB_REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GITHUB_REPO_URL_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$",
    re.IGNORECASE,
)
_PLUGIN_IMPORT_NAMESPACES: dict[str, _PluginImportNamespace] = {}
_ORIGINAL_BUILTIN_IMPORT = builtins.__import__
_PLUGIN_IMPORT_HOOK_INSTALLED = False
_PLUGIN_IMPORT_META_FINDER: _PluginScopedMetaPathFinder | None = None
_PLUGIN_IMPORT_ALIAS_STATE = threading.local()
_TMeta = TypeVar("_TMeta", LimiterMeta, ConversationMeta)


def _default_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _is_valid_github_repo_ref(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    return bool(
        _GITHUB_REPO_NAME_RE.fullmatch(normalized)
        or _GITHUB_REPO_SLUG_RE.fullmatch(normalized)
        or _GITHUB_REPO_URL_RE.fullmatch(normalized)
    )


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
    issues: list[PluginDiscoveryIssue] = field(default_factory=list)


@dataclass(slots=True)
class PluginDiscoveryIssue:
    severity: DiscoverySeverity
    phase: DiscoveryPhase
    plugin_id: str
    message: str
    details: str = ""
    hint: str = ""

    def to_payload(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "phase": self.phase,
            "plugin_id": self.plugin_id,
            "message": self.message,
            "details": self.details,
            "hint": self.hint,
        }


@dataclass(slots=True)
class LoadedHandler:
    descriptor: HandlerDescriptor
    callable: Any
    owner: Any
    plugin_id: str = ""
    local_filters: list[Any] = field(default_factory=list)
    limiter: LimiterMeta | None = None
    conversation: ConversationMeta | None = None


@dataclass(slots=True)
class LoadedCapability:
    descriptor: CapabilityDescriptor
    callable: Any
    owner: Any
    plugin_id: str = ""


@dataclass(slots=True)
class LoadedLLMTool:
    spec: LLMToolSpec
    callable: Any
    owner: Any
    plugin_id: str = ""


@dataclass(slots=True)
class LoadedAgent:
    spec: AgentSpec
    runner_class: type[Any]
    owner: Any | None = None
    plugin_id: str = ""


@dataclass(slots=True)
class LoadedPlugin:
    plugin: PluginSpec
    handlers: list[LoadedHandler]
    capabilities: list[LoadedCapability] = field(default_factory=list)
    llm_tools: list[LoadedLLMTool] = field(default_factory=list)
    agents: list[LoadedAgent] = field(default_factory=list)
    instances: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class _ResolvedComponent:
    cls: type[Any]
    class_path: str
    index: int


@dataclass(slots=True)
class _PluginImportNamespace:
    plugin_id: str
    plugin_dir: Path
    package_name: str


@dataclass(slots=True)
class _ParamTypeInfo:
    type_name: ParamTypeName
    inner_type: OptionalInnerType
    required: bool


class _PluginScopedAliasLoader(importlib.abc.Loader):
    def __init__(self, *, alias_name: str, target_name: str) -> None:
        self.alias_name = alias_name
        self.target_name = target_name

    def create_module(self, spec: ModuleSpec) -> types.ModuleType:
        del spec
        module = sys.modules.get(self.target_name)
        if not isinstance(module, types.ModuleType):
            module = import_module(self.target_name)
        _record_plugin_import_alias(self.alias_name)
        return module

    def exec_module(self, module: types.ModuleType) -> None:
        del module


class _PluginScopedMetaPathFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: types.ModuleType | None = None,
        /,
    ) -> ModuleSpec | None:
        del path, target
        namespace = _plugin_import_namespace_for_current_caller()
        if namespace is None:
            return None
        rewritten_name = _rewrite_plugin_import_name(namespace, fullname)
        if rewritten_name is None:
            return None
        parent_name, _, _ = rewritten_name.rpartition(".")
        parent_search_path = None
        if parent_name:
            parent_module = sys.modules.get(parent_name)
            if not isinstance(parent_module, types.ModuleType):
                parent_module = import_module(parent_name)
            parent_search_path = getattr(parent_module, "__path__", None)
        target_spec = PathFinder.find_spec(
            rewritten_name,
            parent_search_path,
        )
        if target_spec is None:
            return None
        alias_spec = ModuleSpec(
            fullname,
            _PluginScopedAliasLoader(
                alias_name=fullname,
                target_name=rewritten_name,
            ),
            is_package=target_spec.submodule_search_locations is not None,
        )
        alias_spec.origin = target_spec.origin
        alias_spec.cached = target_spec.cached
        alias_spec.has_location = target_spec.has_location
        if target_spec.submodule_search_locations is not None:
            alias_spec.submodule_search_locations = list(
                target_spec.submodule_search_locations
            )
        return alias_spec


def _sanitize_package_component(plugin_id: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", plugin_id).strip("_")
    return sanitized or "plugin"


def _plugin_package_name(plugin_id: str) -> str:
    digest = hashlib.sha256(plugin_id.encode("utf-8")).hexdigest()[:8]
    return f"{_PLUGIN_PACKAGE_PREFIX}{_sanitize_package_component(plugin_id)}_{digest}"


def _plugin_module_name(package_name: str, module_name: str) -> str:
    normalized = module_name.strip()
    return f"{package_name}.{normalized}" if normalized else package_name


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


def _validate_loaded_capability_namespace(
    plugin: PluginSpec,
    *,
    resolved_component: _ResolvedComponent,
    attribute_name: str,
    capability_name: str,
) -> None:
    if capability_belongs_to_plugin(capability_name, plugin.name):
        return
    expected_prefix = plugin_capability_prefix(plugin.name)
    raise ValueError(
        f"{_component_context(plugin, class_path=resolved_component.class_path, index=resolved_component.index)} "
        f"方法 {attribute_name!r} 导出的 capability {capability_name!r} 必须使用当前插件名前缀 "
        f"{expected_prefix!r}，例如 {expected_prefix}<action>"
    )


def _register_loaded_capability_name(
    seen_capability_sources: dict[str, str],
    *,
    capability_name: str,
    source_ref: str,
) -> None:
    existing_source = seen_capability_sources.get(capability_name)
    if existing_source is not None:
        raise ValueError(
            f"capability {capability_name!r} 重复定义：{existing_source} 与 {source_ref}"
        )
    seen_capability_sources[capability_name] = source_ref


def _is_injected_parameter(annotation: Any, parameter_name: str) -> bool:
    return is_framework_injected_parameter(parameter_name, annotation)


def _param_type_name(annotation: Any) -> _ParamTypeInfo:
    normalized, is_optional = unwrap_optional(annotation)
    if normalized is GreedyStr:
        return _ParamTypeInfo("greedy_str", None, False)
    if normalized in {int, float, bool, str}:
        normalized_name = cast(
            Literal["str", "int", "float", "bool"], normalized.__name__
        )
        if is_optional:
            return _ParamTypeInfo("optional", normalized_name, False)
        return _ParamTypeInfo(normalized_name, None, True)
    if is_optional:
        return _ParamTypeInfo("optional", "str", False)
    return _ParamTypeInfo("str", None, True)


def _build_param_specs(handler: Any) -> list[ParamSpec]:
    model_param = resolve_command_model_param(handler)
    if model_param is not None:
        return []
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return []
    try:
        type_hints = typing.get_type_hints(handler)
    except Exception as exc:
        logger.warning(
            "Failed to resolve type hints for handler {}: {}",
            getattr(handler, "__qualname__", repr(handler)),
            exc,
        )
        type_hints = {}

    specs: list[ParamSpec] = []
    for parameter in signature.parameters.values():
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            continue
        annotation = type_hints.get(parameter.name)
        if _is_injected_parameter(annotation, parameter.name):
            continue
        type_info = _param_type_name(annotation)
        required = type_info.required
        if parameter.default is not inspect.Parameter.empty:
            required = False
        specs.append(
            ParamSpec(
                name=parameter.name,
                type=type_info.type_name,
                required=required,
                inner_type=type_info.inner_type,
            )
        )

    greedy_indexes = [
        index for index, spec in enumerate(specs) if spec.type == "greedy_str"
    ]
    if greedy_indexes and greedy_indexes[-1] != len(specs) - 1:
        greedy_spec = specs[greedy_indexes[-1]]
        raise ValueError(f"参数 '{greedy_spec.name}' (GreedyStr) 必须是最后一个参数。")
    return specs


def _validate_schedule_signature(handler: Any) -> None:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return
    allowed_names = {"ctx", "context", "sched", "schedule"}
    invalid = [
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        and parameter.name not in allowed_names
    ]
    if invalid:
        raise ValueError(
            "Schedule handler 只允许注入 ctx/context 和 sched/schedule 参数。"
        )


def _plugin_context(plugin: PluginSpec) -> str:
    return f"插件 '{plugin.name}'（{plugin.manifest_path}）"


def _component_context(plugin: PluginSpec, *, class_path: str, index: int) -> str:
    return f"{_plugin_context(plugin)} 的 components[{index}].class='{class_path}'"


def _resolve_candidate(
    instance: Any,
    name: str,
    meta_getter: typing.Callable[[Any], Any | None],
    *,
    predicate: typing.Callable[[Any], bool] | None = None,
) -> tuple[Any, Any] | None:
    try:
        raw = inspect.getattr_static(instance, name)
    except AttributeError:
        return None

    candidates = [raw]
    wrapped = getattr(raw, "__func__", None)
    if wrapped is not None:
        candidates.append(wrapped)

    for candidate in candidates:
        meta = meta_getter(candidate)
        if meta is None:
            continue
        if predicate is not None and not predicate(meta):
            continue
        try:
            return getattr(instance, name), meta
        except AttributeError:
            return None
    return None


def _resolve_handler_candidate(instance: Any, name: str) -> tuple[Any, Any] | None:
    """Resolve handler candidates without triggering unrelated descriptor side effects."""
    return _resolve_candidate(
        instance,
        name,
        get_handler_meta,
        predicate=lambda meta: meta.trigger is not None,
    )


def _resolve_capability_candidate(instance: Any, name: str) -> tuple[Any, Any] | None:
    return _resolve_candidate(instance, name, get_capability_meta)


def _resolve_llm_tool_candidate(instance: Any, name: str) -> tuple[Any, Any] | None:
    return _resolve_candidate(instance, name, get_llm_tool_meta)


def _iter_agent_candidates(component_cls: type[Any]) -> list[tuple[type[Any], Any]]:
    module = import_module(component_cls.__module__)
    seen: set[str] = set()
    resolved: list[tuple[type[Any], Any]] = []

    def _collect(candidate: Any) -> None:
        if not inspect.isclass(candidate):
            return
        meta = get_agent_meta(candidate)
        if meta is None:
            return
        key = f"{candidate.__module__}.{candidate.__qualname__}"
        if key in seen:
            return
        seen.add(key)
        resolved.append((candidate, meta))

    for candidate in vars(module).values():
        _collect(candidate)
    for candidate in vars(component_cls).values():
        _collect(candidate)
    return resolved


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _read_requirements_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _plugin_config_dir(plugin_dir: Path) -> Path:
    if plugin_dir.parent.name == "plugins" and plugin_dir.parent.parent.exists():
        return plugin_dir.parent.parent / "config"
    return plugin_dir / "data" / "config"


def _plugin_config_path(plugin_dir: Path, plugin_name: str) -> Path:
    return _plugin_config_dir(plugin_dir) / f"{plugin_name}_config.json"


def _read_json_object(
    path: Path,
    *,
    parse_error_message: str,
    read_error_message: str,
    non_object_message: str | None = None,
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning(parse_error_message, path, exc)
        return {}
    except OSError as exc:
        logger.warning(read_error_message, path, exc)
        return {}
    if isinstance(payload, dict):
        return payload
    if non_object_message is not None:
        logger.warning(non_object_message, path, type(payload).__name__)
    return {}


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


def load_plugin_config_schema(plugin: PluginSpec) -> dict[str, Any]:
    """加载插件配置 schema，解析失败时记录日志并返回空对象。"""
    schema_path = plugin.plugin_dir / CONFIG_SCHEMA_FILE
    if not schema_path.exists():
        return {}
    return _read_json_object(
        schema_path,
        parse_error_message="Failed to parse SDK plugin config schema {}: {}",
        read_error_message="Failed to read SDK plugin config schema {}: {}",
        non_object_message="SDK plugin config schema {} must be a JSON object, got {}",
    )


def save_plugin_config(
    plugin: PluginSpec,
    payload: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按 schema 归一化并写回插件配置。"""
    active_schema = (
        load_plugin_config_schema(plugin) if schema is None else dict(schema)
    )
    normalized = {
        key: _normalize_config_value(field_schema, payload.get(key))
        for key, field_schema in active_schema.items()
        if isinstance(field_schema, dict)
    }

    config_path = _plugin_config_path(plugin.plugin_dir, plugin.name)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def load_plugin_config(
    plugin: PluginSpec,
    *,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """加载插件配置，返回普通字典。"""
    active_schema = (
        load_plugin_config_schema(plugin) if schema is None else dict(schema)
    )
    if not active_schema:
        return {}

    config_path = _plugin_config_path(plugin.plugin_dir, plugin.name)
    existing = (
        _read_json_object(
            config_path,
            parse_error_message="Failed to parse SDK plugin config {}: {}",
            read_error_message="Failed to read SDK plugin config {}: {}",
        )
        if config_path.exists()
        else {}
    )
    normalized = {
        key: _normalize_config_value(field_schema, existing.get(key))
        for key, field_schema in active_schema.items()
        if isinstance(field_schema, dict)
    }

    if not config_path.exists() or normalized != existing:
        save_plugin_config(plugin, normalized, schema=active_schema)
    return normalized


def _is_new_star_component(cls: type[Any]) -> bool:
    """检查组件类是否为 astrbot-sdk 新版 Star。"""
    return bool(getattr(cls, "__astrbot_is_new_star__", False))


def _plugin_component_classes(plugin: PluginSpec) -> list[_ResolvedComponent]:
    """解析插件组件类列表。"""
    components = plugin.manifest_data.get("components") or []
    if not isinstance(components, list):
        return []

    classes: list[_ResolvedComponent] = []
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise ValueError(
                f"{_plugin_context(plugin)} 的 components[{index}] 必须是 object。"
            )
        class_path = component.get("class")
        if not isinstance(class_path, str) or ":" not in class_path:
            raise ValueError(
                f"{_plugin_context(plugin)} 的 components[{index}].class "
                "必须是 '<module>:<Class>'。"
            )
        try:
            cls = _import_plugin_string(class_path, plugin)
        except Exception as exc:
            raise ValueError(
                f"{_component_context(plugin, class_path=class_path, index=index)} "
                f"加载失败：{exc}"
            ) from exc
        if not isinstance(cls, type):
            raise ValueError(
                f"{_component_context(plugin, class_path=class_path, index=index)} "
                "解析结果不是类，请检查导出名称。"
            )
        classes.append(
            _ResolvedComponent(
                cls=cls,
                class_path=class_path,
                index=index,
            )
        )
    if not classes:
        raise ValueError(
            f"{_plugin_context(plugin)} 未声明任何可加载组件。"
            "请检查 plugin.yaml 中的 components 配置。"
        )
    return classes


def load_plugin_spec(plugin_dir: Path) -> PluginSpec:
    """从插件目录加载插件规范。"""
    plugin_dir = plugin_dir.resolve()
    manifest_path = plugin_dir / PLUGIN_MANIFEST_FILE
    requirements_path = plugin_dir / "requirements.txt"

    if not manifest_path.exists():
        raise ValueError(f"插件目录 '{plugin_dir}' 缺少 {PLUGIN_MANIFEST_FILE}。")

    manifest_data = _read_yaml(manifest_path)
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
    manifest_label = f"插件 '{plugin.name}'（{plugin.manifest_path}）"

    raw_name = manifest_data.get("name")
    if not isinstance(raw_name, str) or not raw_name:
        raise ValueError(f"{manifest_label} 缺少 name。")
    try:
        validate_plugin_id(raw_name)
    except ValueError as exc:
        raise ValueError(f"{manifest_label} 的 name 不合法：{exc}") from exc

    raw_runtime = manifest_data.get("runtime") or {}
    raw_python = raw_runtime.get("python")
    if not isinstance(raw_python, str) or not raw_python:
        raise ValueError(f"{manifest_label} 缺少 runtime.python。")

    raw_author = manifest_data.get("author")
    if not isinstance(raw_author, str) or not raw_author.strip():
        raise ValueError(f"{manifest_label} 缺少 author。")

    raw_repo = manifest_data.get("repo")
    if not isinstance(raw_repo, str) or not raw_repo.strip():
        raise ValueError(f"{manifest_label} 缺少 repo。")
    if not _is_valid_github_repo_ref(raw_repo):
        raise ValueError(
            f"{manifest_label} 的 repo 不合法："
            "请填写 GitHub 仓库名（repo）、owner/repo，或 https://github.com/owner/repo。"
        )

    components = manifest_data.get("components")
    if not isinstance(components, list):
        raise ValueError(f"{manifest_label} 的 components 必须是数组。")

    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise ValueError(f"{manifest_label} 的 components[{index}] 必须是 object。")
        class_path = component.get("class")
        if not isinstance(class_path, str) or ":" not in class_path:
            raise ValueError(
                f"{manifest_label} 的 components[{index}].class "
                "必须是 '<module>:<Class>'。"
            )


# TODO: 不能保证插件和命令冲突消失，真有那么一天我们sdk小团体也是好起来了
def discover_plugins(plugins_dir: Path) -> PluginDiscoveryResult:
    """扫描目录发现所有插件。"""
    plugins_root = plugins_dir.resolve()
    skipped_plugins: dict[str, str] = {}
    issues: list[PluginDiscoveryIssue] = []
    plugins: list[PluginSpec] = []
    # TODO: 改用 dict 记录 name -> plugin_dir 映射，以便在重复时报错时显示冲突路径
    seen_name_sources: dict[str, Path] = {}  # plugin_name -> plugin_dir

    if not plugins_root.exists():
        return PluginDiscoveryResult([], {}, [])

    for entry in sorted(plugins_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        manifest_path = entry / PLUGIN_MANIFEST_FILE
        if not manifest_path.exists():
            continue

        plugin: PluginSpec | None = None
        try:
            plugin = load_plugin_spec(entry)
            validate_plugin_spec(plugin)
        except Exception as exc:
            skip_key = entry.name
            if plugin is not None:
                raw_name = plugin.manifest_data.get("name")
                if isinstance(raw_name, str) and raw_name:
                    skip_key = raw_name
            details = str(exc)
            skipped_plugins[skip_key] = f"failed to parse plugin manifest: {details}"
            issues.append(
                PluginDiscoveryIssue(
                    severity="error",
                    phase="discovery",
                    plugin_id=skip_key,
                    message="插件发现失败",
                    details=details,
                )
            )
            continue

        plugin_name = plugin.name
        if not isinstance(plugin_name, str) or not plugin_name:
            skipped_plugins[entry.name] = "plugin name is required"
            issues.append(
                PluginDiscoveryIssue(
                    severity="error",
                    phase="discovery",
                    plugin_id=entry.name,
                    message="插件缺少名称",
                    details="plugin name is required",
                )
            )
            continue
        if plugin_name in seen_name_sources:
            existing_source = seen_name_sources.get(plugin_name, Path("<unknown>"))
            skipped_plugins[plugin_name] = "duplicate plugin name"
            issues.append(
                PluginDiscoveryIssue(
                    severity="error",
                    phase="discovery",
                    plugin_id=plugin_name,
                    message="插件名称重复",
                    details=f"冲突的插件目录：{existing_source} 与 {plugin.plugin_dir}",
                    hint="请修改其中一个插件的名称后重试",
                )
            )
            continue
        seen_name_sources[plugin_name] = plugin.plugin_dir
        plugins.append(plugin)

    return PluginDiscoveryResult(
        plugins=plugins,
        skipped_plugins=skipped_plugins,
        issues=issues,
    )


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
        前插件的最小规划，以保证旧的"单插件直接调用"模式仍然可用。
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
        return _read_json_object(
            state_path,
            parse_error_message="Failed to parse plugin worker state {}: {}",
            read_error_message="Failed to read plugin worker state {}: {}",
        )

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


def _copy_meta(meta: _TMeta | None) -> _TMeta | None:
    if meta is None:
        return None
    # Use dataclass-level cloning so metadata schema changes do not silently
    # drift away from the loader's copy helpers.
    return replace(meta)


def _validate_handler_kind(
    plugin: PluginSpec,
    *,
    resolved_component: _ResolvedComponent,
    attribute_name: str,
    kind: str,
) -> HandlerKind:
    if kind in _VALID_HANDLER_KINDS:
        return cast(HandlerKind, kind)
    raise ValueError(
        f"{_component_context(plugin, class_path=resolved_component.class_path, index=resolved_component.index)} "
        f"方法 {attribute_name!r} 的 handler kind {kind!r} 不合法；"
        f"允许的值为 {', '.join(_VALID_HANDLER_KINDS)}。"
    )


def _load_component_instance(
    plugin: PluginSpec,
    resolved_component: _ResolvedComponent,
) -> Any:
    component_cls = resolved_component.cls
    if not _is_new_star_component(component_cls):
        raise ValueError(
            f"{_component_context(plugin, class_path=resolved_component.class_path, index=resolved_component.index)} "
            f"解析到的类 {component_cls.__module__}.{component_cls.__qualname__} "
            "不是 astrbot-sdk Star 组件。请继承 astrbot_sdk.Star。"
        )
    try:
        instance = component_cls()
    except Exception as exc:
        raise ValueError(
            f"{_component_context(plugin, class_path=resolved_component.class_path, index=resolved_component.index)} "
            f"实例化失败：{exc}"
        ) from exc
    logger.debug(
        "Instantiated SDK plugin component {} for plugin {}",
        resolved_component.class_path,
        plugin.name,
    )
    return instance


def _collect_component_agents(
    plugin: PluginSpec,
    component_cls: type[Any],
    *,
    seen_agents: set[str],
) -> list[LoadedAgent]:
    agents: list[LoadedAgent] = []
    for runner_class, meta in _iter_agent_candidates(component_cls):
        runner_key = f"{runner_class.__module__}.{runner_class.__qualname__}"
        if runner_key in seen_agents:
            continue
        seen_agents.add(runner_key)
        agents.append(
            LoadedAgent(
                spec=meta.spec.model_copy(deep=True),
                runner_class=runner_class,
                owner=None,
                plugin_id=plugin.name,
            )
        )
    return agents


def _build_loaded_handler(
    plugin: PluginSpec,
    *,
    resolved_component: _ResolvedComponent,
    instance: Any,
    attribute_name: str,
    bound: Any,
    meta: Any,
) -> LoadedHandler:
    handler_kind = _validate_handler_kind(
        plugin,
        resolved_component=resolved_component,
        attribute_name=attribute_name,
        kind=meta.kind,
    )
    handler_id = (
        f"{plugin.name}:{instance.__class__.__module__}.{instance.__class__.__name__}."
        f"{attribute_name}"
    )
    if isinstance(meta.trigger, ScheduleTrigger):
        _validate_schedule_signature(bound)
    param_specs = _build_param_specs(bound)
    return LoadedHandler(
        descriptor=HandlerDescriptor(
            id=handler_id,
            trigger=meta.trigger,
            kind=handler_kind,
            contract=meta.contract,
            description=meta.description,
            priority=meta.priority,
            permissions=meta.permissions.model_copy(deep=True),
            filters=[item.model_copy(deep=True) for item in meta.filters],
            param_specs=[item.model_copy(deep=True) for item in param_specs],
            command_route=(
                meta.command_route.model_copy(deep=True)
                if meta.command_route is not None
                else None
            ),
        ),
        callable=bound,
        owner=instance,
        plugin_id=plugin.name,
        local_filters=list(meta.local_filters),
        limiter=_copy_meta(meta.limiter),
        conversation=_copy_meta(meta.conversation),
    )


def _collect_component_members(
    plugin: PluginSpec,
    *,
    resolved_component: _ResolvedComponent,
    instance: Any,
    seen_capability_sources: dict[str, str],
) -> tuple[list[LoadedHandler], list[LoadedCapability], list[LoadedLLMTool]]:
    handlers: list[LoadedHandler] = []
    capabilities: list[LoadedCapability] = []
    llm_tools: list[LoadedLLMTool] = []

    for name in _iter_discoverable_names(instance):
        resolved = _resolve_handler_candidate(instance, name)
        capability = _resolve_capability_candidate(instance, name)
        llm_tool = _resolve_llm_tool_candidate(instance, name)
        if resolved is None and capability is None and llm_tool is None:
            continue
        if capability is not None:
            bound_capability, capability_meta = capability
            capability_name = capability_meta.descriptor.name
            _validate_loaded_capability_namespace(
                plugin,
                resolved_component=resolved_component,
                attribute_name=name,
                capability_name=capability_name,
            )
            _register_loaded_capability_name(
                seen_capability_sources,
                capability_name=capability_name,
                source_ref=f"{resolved_component.class_path}.{name}",
            )
            capabilities.append(
                LoadedCapability(
                    descriptor=capability_meta.descriptor.model_copy(deep=True),
                    callable=bound_capability,
                    owner=instance,
                    plugin_id=plugin.name,
                )
            )
        if llm_tool is not None:
            bound_tool, tool_meta = llm_tool
            llm_tools.append(
                LoadedLLMTool(
                    spec=tool_meta.spec.model_copy(deep=True),
                    callable=bound_tool,
                    owner=instance,
                    plugin_id=plugin.name,
                )
            )
        if resolved is not None:
            bound_handler, handler_meta = resolved
            handlers.append(
                _build_loaded_handler(
                    plugin,
                    resolved_component=resolved_component,
                    instance=instance,
                    attribute_name=name,
                    bound=bound_handler,
                    meta=handler_meta,
                )
            )
    return handlers, capabilities, llm_tools


def load_plugin(plugin: PluginSpec) -> LoadedPlugin:
    """加载插件，返回处理器和能力列表。

    仅支持 astrbot-sdk 新版 Star 组件（无参构造函数）。
    """
    with _PLUGIN_IMPORT_LOCK:
        logger.debug("Loading SDK plugin {} from {}", plugin.name, plugin.plugin_dir)
        _ensure_plugin_import_hook_installed()
        namespace = _register_plugin_import_namespace(plugin)
        _purge_plugin_bytecode(plugin.plugin_dir)
        _purge_plugin_package(namespace.package_name)
        _purge_plugin_modules(plugin.plugin_dir)
        _prepare_plugin_import(plugin.plugin_dir)
        _ensure_plugin_package(namespace)
        importlib.invalidate_caches()

        instances: list[Any] = []
        handlers: list[LoadedHandler] = []
        capabilities: list[LoadedCapability] = []
        llm_tools: list[LoadedLLMTool] = []
        agents: list[LoadedAgent] = []
        seen_agents: set[str] = set()
        seen_capability_sources: dict[str, str] = {}
        with caller_plugin_scope(plugin.name):
            resolved_components = _plugin_component_classes(plugin)

            for resolved_component in resolved_components:
                instance = _load_component_instance(plugin, resolved_component)
                instances.append(instance)
                agents.extend(
                    _collect_component_agents(
                        plugin,
                        resolved_component.cls,
                        seen_agents=seen_agents,
                    )
                )
                component_handlers, component_capabilities, component_tools = (
                    _collect_component_members(
                        plugin,
                        resolved_component=resolved_component,
                        instance=instance,
                        seen_capability_sources=seen_capability_sources,
                    )
                )
                handlers.extend(component_handlers)
                capabilities.extend(component_capabilities)
                llm_tools.extend(component_tools)

        logger.debug(
            "Loaded SDK plugin {}: {} components, {} handlers, {} capabilities, {} llm tools, {} agents",
            plugin.name,
            len(resolved_components),
            len(handlers),
            len(capabilities),
            len(llm_tools),
            len(agents),
        )
        return LoadedPlugin(
            plugin=plugin,
            handlers=handlers,
            capabilities=capabilities,
            llm_tools=llm_tools,
            agents=agents,
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


def _register_plugin_import_namespace(plugin: PluginSpec) -> _PluginImportNamespace:
    existing = _PLUGIN_IMPORT_NAMESPACES.get(plugin.name)
    package_name = (
        existing.package_name
        if existing is not None
        else _plugin_package_name(plugin.name)
    )
    namespace = _PluginImportNamespace(
        plugin_id=plugin.name,
        plugin_dir=plugin.plugin_dir.resolve(),
        package_name=package_name,
    )
    _PLUGIN_IMPORT_NAMESPACES[plugin.name] = namespace
    return namespace


def _ensure_plugin_package(namespace: _PluginImportNamespace) -> types.ModuleType:
    existing = sys.modules.get(namespace.package_name)
    if isinstance(existing, types.ModuleType):
        existing.__path__ = [str(namespace.plugin_dir)]
        existing.__package__ = namespace.package_name
        return existing

    module = types.ModuleType(namespace.package_name)
    module.__file__ = str(namespace.plugin_dir)
    module.__package__ = namespace.package_name
    module.__path__ = [str(namespace.plugin_dir)]
    module.__loader__ = None
    spec = ModuleSpec(
        namespace.package_name,
        loader=None,
        is_package=True,
    )
    spec.submodule_search_locations = [str(namespace.plugin_dir)]
    module.__spec__ = spec
    sys.modules[namespace.package_name] = module
    return module


def _prepare_plugin_import(plugin_dir: Path) -> None:
    plugin_path = str(plugin_dir.resolve())
    sys.path[:] = [entry for entry in sys.path if entry != plugin_path]
    sys.path.insert(0, plugin_path)


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


def _purge_plugin_modules(plugin_dir: Path) -> None:
    plugin_root = plugin_dir.resolve()
    for module_name, module in list(sys.modules.items()):
        if module is None:
            continue
        if _module_belongs_to_plugin(module, plugin_root):
            sys.modules.pop(module_name, None)


def _purge_plugin_package(package_name: str) -> None:
    for module_name in list(sys.modules):
        if module_name == package_name or module_name.startswith(f"{package_name}."):
            sys.modules.pop(module_name, None)


def _purge_plugin_bytecode(plugin_dir: Path) -> None:
    plugin_root = plugin_dir.resolve()
    for path in plugin_root.rglob("*"):
        try:
            if path.is_dir() and path.name == "__pycache__":
                shutil.rmtree(path, ignore_errors=True)
                continue
            if path.is_file() and path.suffix in {".pyc", ".pyo"}:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def _import_plugin_string(path: str, plugin: PluginSpec) -> Any:
    module_name, attr = path.split(":", 1)
    namespace = _PLUGIN_IMPORT_NAMESPACES.get(plugin.name)
    if namespace is None:
        raise RuntimeError(f"plugin import namespace missing: {plugin.name}")
    module = import_module(_plugin_module_name(namespace.package_name, module_name))
    return getattr(module, attr)


def _plugin_import_namespace_for_current_caller() -> _PluginImportNamespace | None:
    plugin_id = current_caller_plugin_id()
    if not plugin_id:
        return None
    return _PLUGIN_IMPORT_NAMESPACES.get(plugin_id)


def _rewrite_plugin_import_name(
    namespace: _PluginImportNamespace,
    name: str,
) -> str | None:
    normalized = name.strip()
    if not normalized:
        return None
    if normalized.startswith(_PLUGIN_PACKAGE_PREFIX):
        return None
    root_name = normalized.split(".", 1)[0]
    if not _plugin_defines_module_root(namespace.plugin_dir, root_name):
        return None
    return _plugin_module_name(namespace.package_name, normalized)


def _plugin_import_alias_buckets() -> list[set[str]]:
    buckets = getattr(_PLUGIN_IMPORT_ALIAS_STATE, "buckets", None)
    if buckets is None:
        buckets = []
        _PLUGIN_IMPORT_ALIAS_STATE.buckets = buckets
    return buckets


def _push_plugin_import_alias_bucket() -> set[str]:
    bucket: set[str] = set()
    _plugin_import_alias_buckets().append(bucket)
    return bucket


def _pop_plugin_import_alias_bucket(bucket: set[str]) -> set[str]:
    buckets = _plugin_import_alias_buckets()
    if buckets and buckets[-1] is bucket:
        buckets.pop()
    else:
        with contextlib.suppress(ValueError):
            buckets.remove(bucket)
    return bucket


def _record_plugin_import_alias(alias_name: str) -> None:
    normalized = alias_name.strip()
    if not normalized or normalized.startswith(_PLUGIN_PACKAGE_PREFIX):
        return
    buckets = _plugin_import_alias_buckets()
    if not buckets:
        return
    buckets[-1].add(normalized)


def _cleanup_plugin_import_aliases(alias_names: set[str]) -> None:
    for alias_name in sorted(
        alias_names, key=lambda item: item.count("."), reverse=True
    ):
        sys.modules.pop(alias_name, None)


def _plugin_scoped_import(
    name: str,
    globals: dict[str, Any] | None = None,
    locals: dict[str, Any] | None = None,
    fromlist: tuple[Any, ...] | list[Any] = (),
    level: int = 0,
) -> Any:
    with _PLUGIN_IMPORT_LOCK:
        alias_bucket = _push_plugin_import_alias_bucket()
        try:
            return _ORIGINAL_BUILTIN_IMPORT(name, globals, locals, fromlist, level)
        finally:
            _cleanup_plugin_import_aliases(
                _pop_plugin_import_alias_bucket(alias_bucket)
            )


def _ensure_plugin_import_meta_finder_installed() -> None:
    global _PLUGIN_IMPORT_META_FINDER
    if (
        _PLUGIN_IMPORT_META_FINDER is not None
        and _PLUGIN_IMPORT_META_FINDER in sys.meta_path
    ):
        return
    finder = _PluginScopedMetaPathFinder()
    sys.meta_path.insert(0, finder)
    _PLUGIN_IMPORT_META_FINDER = finder


def _ensure_plugin_import_hook_installed() -> None:
    global _PLUGIN_IMPORT_HOOK_INSTALLED
    _ensure_plugin_import_meta_finder_installed()
    # 防御性检查：如果 hook 已在位，只补全标志位，不重复安装
    if builtins.__import__ is _plugin_scoped_import:
        _PLUGIN_IMPORT_HOOK_INSTALLED = True
        return
    # 标志位声称已安装但实际 builtin 已被外部篡改（如测试框架 monkeypatch），
    # 需要重置标志位以触发重新安装
    if (
        _PLUGIN_IMPORT_HOOK_INSTALLED
        and builtins.__import__ is not _plugin_scoped_import
    ):
        _PLUGIN_IMPORT_HOOK_INSTALLED = False
    if _PLUGIN_IMPORT_HOOK_INSTALLED:
        return
    builtins.__import__ = _plugin_scoped_import
    _PLUGIN_IMPORT_HOOK_INSTALLED = True


def _restore_plugin_import_hook() -> None:
    """还原 builtin __import__，用于插件卸载或测试 teardown 时清理全局状态。"""
    global _PLUGIN_IMPORT_HOOK_INSTALLED, _PLUGIN_IMPORT_META_FINDER
    if builtins.__import__ is _plugin_scoped_import:
        builtins.__import__ = _ORIGINAL_BUILTIN_IMPORT
    if _PLUGIN_IMPORT_META_FINDER is not None:
        with contextlib.suppress(ValueError):
            sys.meta_path.remove(_PLUGIN_IMPORT_META_FINDER)
        _PLUGIN_IMPORT_META_FINDER = None
    _PLUGIN_IMPORT_HOOK_INSTALLED = False


def import_string(path: str, plugin_dir: Path | None = None) -> Any:
    """通过字符串路径导入对象。"""
    with _PLUGIN_IMPORT_LOCK:
        module_name, attr = path.split(":", 1)
        module = import_module(module_name)
        return getattr(module, attr)
