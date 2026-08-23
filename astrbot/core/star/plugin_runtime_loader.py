"""Plugin discovery, import, declaration collection, and initialization."""

from __future__ import annotations

import functools
import json
import keyword
import logging
import os
import re
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, NotRequired, TypedDict

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from astrbot import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import VERSION
from astrbot.core.execution_context import CoreExecutionContext
from astrbot.core.utils.requirements_utils import plan_missing_requirements_install
from astrbot.core.utils.shared_preferences import SharedPreferences

from .command_ids import take_alter_cmd_entry
from .command_management import command_id_for_handler, sync_command_configs
from .dashboard_extension import validate_dashboard_manifest
from .filter.permission import ActionPermissionFilter
from .plugin_catalog import PluginCatalog
from .plugin_context import PluginContext
from .plugin_extension_coordinator import PluginExtensionCoordinator
from .plugin_package_installer import PluginPackageInstaller
from .plugin_runtime_common import (
    ImportDependencyRecoveryMode,
    ImportDependencyRecoveryState,
    PluginVersionUnsupportedError,
)
from .register.star_handler import collect_plugin_module_declarations
from .star import StarMetadata, collect_star_declaration
from .star_handler import EventType

import_module = __import__


class PluginModuleEntry(TypedDict):
    """One discoverable plugin entry module."""

    pname: str
    module: str
    module_path: str
    reserved: NotRequired[bool]


class PluginRuntimeLoader:
    """Load plugin packages into one isolated runtime catalog.

    It owns import-time state and failure records.  A caller must go through
    :class:`PluginLifecycle` for operations that change the live runtime after
    loading, such as command refreshes and hot reloads.
    """

    def __init__(
        self,
        *,
        execution_context: CoreExecutionContext,
        catalog: PluginCatalog,
        extensions: PluginExtensionCoordinator,
        plugin_context: PluginContext,
        preferences: SharedPreferences,
        packages: PluginPackageInstaller,
        plugin_store_path: str,
        plugin_config_path: str,
        reserved_plugin_path: str,
        module_importer: Callable[..., ModuleType] | None = None,
        after_module_materialized: Callable[[], None] | None = None,
    ) -> None:
        self._execution_context = execution_context
        self._catalog = catalog
        self._extensions = extensions
        self._plugin_context = plugin_context
        self._preferences = preferences
        self._packages = packages
        self._plugin_store_path = plugin_store_path
        self._plugin_config_path = plugin_config_path
        self._reserved_plugin_path = reserved_plugin_path
        # Reload staging supplies these two hooks to confine its temporary
        # module-cache substitution to synchronous import/materialization.
        # Ordinary loads continue to use the process import function directly.
        self._module_importer = module_importer
        self._after_module_materialized = after_module_materialized
        self._failed_plugins: dict[str, dict[str, Any]] = {}
        self._failed_plugin_info = ""

    @property
    def failure_info(self) -> str:
        """Return a rendered, read-only summary of failed plugin loads."""
        return self._failed_plugin_info

    @property
    def bundled_store_path(self) -> str:
        """Return the immutable bundled-plugin root used for discovery."""
        return self._reserved_plugin_path

    def failed_plugins(self) -> dict[str, dict[str, Any]]:
        """Return an isolated snapshot of failed plugin diagnostics."""
        return {name: dict(info) for name, info in self._failed_plugins.items()}

    def failed_plugin(self, dir_name: str) -> dict[str, Any] | None:
        """Return a snapshot for one failed plugin directory."""
        info = self._failed_plugins.get(dir_name)
        return dict(info) if info is not None else None

    @staticmethod
    def get_modules(path: str) -> list[PluginModuleEntry]:
        """Find packages that use the required ``main.py`` entry point."""
        modules: list[PluginModuleEntry] = []
        for name in os.listdir(path):
            if not os.path.isdir(os.path.join(path, name)):
                continue
            if not os.path.exists(os.path.join(path, name, "main.py")):
                logger.info("插件 %s 未找到 main.py，跳过。", name)
                continue
            modules.append(
                {
                    "pname": name,
                    "module": "main",
                    "module_path": os.path.join(path, name, "main"),
                },
            )
        return modules

    def discover_modules(self) -> list[PluginModuleEntry]:
        """Discover bundled and user plugin entry modules."""
        modules: list[PluginModuleEntry] = []
        if os.path.exists(self._plugin_store_path):
            modules.extend(self.get_modules(self._plugin_store_path))
        if os.path.exists(self._reserved_plugin_path):
            for module in self.get_modules(self._reserved_plugin_path):
                module["reserved"] = True
                modules.append(module)
        return modules

    @staticmethod
    def load_i18n(plugin_path: str) -> dict[str, dict]:
        """Read the bounded, supported plugin translation files."""
        i18n_dir = Path(plugin_path, ".astrbot-plugin", "i18n")
        if not i18n_dir.is_dir():
            return {}

        translations: dict[str, dict] = {}
        try:
            for file_path in i18n_dir.iterdir():
                if file_path.suffix.lower() != ".json":
                    continue
                locale = file_path.stem
                if not locale or len(locale) > 32 or locale not in {"zh-CN", "en-US"}:
                    logger.warning("不支持的插件 i18n locale，已跳过: %s", file_path)
                    continue
                if not file_path.is_file():
                    continue
                if file_path.stat().st_size > 1024 * 1024:
                    logger.warning("插件 i18n 文件超过 1MB，已跳过: %s", file_path)
                    continue
                try:
                    with file_path.open(encoding="utf-8-sig") as handle:
                        locale_data = json.load(handle)
                    if isinstance(locale_data, dict):
                        translations[locale] = locale_data
                    else:
                        logger.warning(
                            "插件 i18n 文件内容不是 JSON object，已跳过: %s",
                            file_path,
                        )
                except Exception as exc:
                    logger.warning("加载插件 i18n 文件失败 %s: %s", file_path, exc)
        except OSError as exc:
            logger.warning("读取插件 i18n 目录失败 %s: %s", i18n_dir, exc)
        return translations

    @classmethod
    def load_metadata(cls, plugin_path: str) -> StarMetadata:
        """Validate and load ``metadata.yaml`` for one package directory."""
        if not os.path.exists(plugin_path):
            raise Exception("插件不存在。")
        metadata_path = os.path.join(plugin_path, "metadata.yaml")
        if not os.path.exists(metadata_path):
            raise Exception("未找到 metadata.yaml。")
        with open(metadata_path, encoding="utf-8") as handle:
            metadata = yaml.safe_load(handle)
        if not isinstance(metadata, dict):
            raise Exception("metadata.yaml 格式错误。")
        if not {"name", "desc", "version", "author"}.issubset(metadata):
            raise Exception(
                "插件元数据信息不完整。name, desc, version, author 是必须的字段。",
            )
        plugin_root = Path(plugin_path).resolve(strict=True)
        dashboard = validate_dashboard_manifest(metadata, plugin_root)
        authorization_actions = cls._load_authorization_actions(metadata)
        return StarMetadata(
            name=metadata["name"],
            author=metadata["author"],
            desc=metadata["desc"],
            short_desc=(
                metadata["short_desc"]
                if isinstance(metadata.get("short_desc"), str)
                else None
            ),
            version=metadata["version"],
            repo=metadata.get("repo"),
            display_name=metadata.get("display_name"),
            support_platforms=(
                [
                    item
                    for item in metadata["support_platforms"]
                    if isinstance(item, str)
                ]
                if isinstance(metadata.get("support_platforms"), list)
                else []
            ),
            astrbot_version=(
                metadata["astrbot_version"]
                if isinstance(metadata.get("astrbot_version"), str)
                else None
            ),
            dashboard=dashboard,
            dashboard_root=plugin_root,
            i18n=cls.load_i18n(plugin_path),
            authorization_actions=authorization_actions,
        )

    @staticmethod
    def _load_authorization_actions(metadata: dict) -> frozenset[str]:
        """Validate a plugin's small, namespaced action declaration."""

        raw_authorization = metadata.get("authorization", {})
        if raw_authorization is None:
            return frozenset()
        if not isinstance(raw_authorization, dict):
            raise ValueError("metadata.yaml authorization must be an object")
        raw_actions = raw_authorization.get("actions", [])
        if not isinstance(raw_actions, list):
            raise ValueError("metadata.yaml authorization.actions must be a list")
        name = metadata.get("name")
        author = metadata.get("author")
        if not isinstance(name, str) or not isinstance(author, str):
            raise ValueError("Plugin identity is required for authorization actions")
        plugin_id = (
            f"{author.lower().replace('/', '_')}/{name.lower().replace('/', '_')}"
        )
        actions: set[str] = set()
        for item in raw_actions:
            action = item.get("id") if isinstance(item, dict) else item
            if not isinstance(action, str) or not re.fullmatch(
                r"[a-z][a-z0-9_.-]{0,63}", action
            ):
                raise ValueError("Plugin authorization action id is invalid")
            actions.add(f"plugin:{plugin_id}:{action}")
        return frozenset(actions)

    @staticmethod
    def normalize_plugin_dir_name(plugin_name: str) -> str:
        """Normalize the directory name declared by metadata."""
        return plugin_name.strip()

    @staticmethod
    def validate_importable_name(plugin_name: str) -> None:
        """Reject metadata values that cannot safely become a module name."""
        if "/" in plugin_name or "\\" in plugin_name:
            raise ValueError(
                "metadata.yaml 中 name 含有路径分隔符，不可用于 importlib 加载。"
            )
        if not plugin_name.isidentifier() or keyword.iskeyword(plugin_name):
            raise Exception(
                "metadata.yaml 中 name 不是合法的模块名称（应为合法 Python 标识符且非关键字）。",
            )

    @classmethod
    def plugin_dir_name_from_metadata(cls, plugin_path: str) -> str:
        """Return the validated package directory name from metadata."""
        metadata_path = os.path.join(plugin_path, "metadata.yaml")
        if not os.path.exists(metadata_path):
            raise Exception("未找到 metadata.yaml，无法获取插件目录名。")
        with open(metadata_path, encoding="utf-8") as handle:
            metadata = yaml.safe_load(handle)
        if not isinstance(metadata, dict):
            raise Exception("metadata.yaml 格式错误。")
        plugin_name = metadata.get("name")
        if not isinstance(plugin_name, str) or not plugin_name.strip():
            raise Exception("metadata.yaml 中缺少 name 字段。")
        dir_name = cls.normalize_plugin_dir_name(plugin_name)
        if not dir_name:
            raise Exception("metadata.yaml 中 name 字段内容非法。")
        cls.validate_importable_name(dir_name)
        return dir_name

    @staticmethod
    def validate_astrbot_version_specifier(
        version_spec: str | None,
    ) -> tuple[bool, str | None]:
        """Check an optional PEP 440 plugin version range."""
        if not version_spec or not version_spec.strip():
            return True, None
        normalized_spec = version_spec.strip()
        try:
            specifier = SpecifierSet(normalized_spec)
        except InvalidSpecifier:
            return (
                False,
                "Invalid astrbot_version. Use a PEP 440 range, e.g. >=4.16,<5.",
            )
        try:
            current_version = Version(VERSION)
        except InvalidVersion:
            return (
                False,
                f"Invalid current AstrBot version: {VERSION}. Cannot check plugin version range.",
            )
        if not specifier.contains(current_version, prereleases=True):
            return (
                False,
                f"AstrBot {VERSION} does not satisfy plugin astrbot_version: {normalized_spec}",
            )
        return True, None

    @staticmethod
    def _recovery_state(
        requirements_path: str,
        *,
        reserved: bool,
    ) -> ImportDependencyRecoveryState:
        if reserved or not os.path.exists(requirements_path):
            return ImportDependencyRecoveryState(ImportDependencyRecoveryMode.DISABLED)
        install_plan = plan_missing_requirements_install(requirements_path)
        if install_plan is None:
            return ImportDependencyRecoveryState(
                ImportDependencyRecoveryMode.RECOVER_ON_FAILURE,
            )
        if install_plan.version_mismatch_names:
            return ImportDependencyRecoveryState(
                ImportDependencyRecoveryMode.REINSTALL_ON_FAILURE,
                install_plan=install_plan,
            )
        return ImportDependencyRecoveryState(
            ImportDependencyRecoveryMode.PRELOAD_AND_RECOVER,
            install_plan=install_plan,
        )

    def _try_import_from_installed_dependencies(
        self,
        *,
        path: str,
        module_str: str,
        root_dir_name: str,
        requirements_path: str,
        import_exc: Exception,
        module_importer: Callable[..., ModuleType],
    ) -> ModuleType | None:
        try:
            logger.info(
                "插件 %s 导入失败，尝试从已安装依赖恢复: %s",
                root_dir_name,
                import_exc,
            )
            self._packages.prefer_installed_dependencies(requirements_path)
            module = module_importer(path, fromlist=[module_str])
            logger.info(
                "插件 %s 已从 site-packages 恢复依赖，跳过重新安装。", root_dir_name
            )
            return module
        except (ImportError, ModuleNotFoundError) as recover_exc:
            logger.info(
                "插件 %s 已安装依赖恢复失败，将重新安装依赖: %s",
                root_dir_name,
                recover_exc,
            )
            return None

    async def import_with_dependency_recovery(
        self,
        *,
        path: str,
        module_str: str,
        root_dir_name: str,
        requirements_path: str,
        reserved: bool = False,
    ) -> ModuleType:
        """Import a plugin and recover missing non-bundled requirements."""
        module_importer = self._module_importer or import_module
        recovery_state = self._recovery_state(requirements_path, reserved=reserved)
        if recovery_state.mode is ImportDependencyRecoveryMode.PRELOAD_AND_RECOVER:
            try:
                self._packages.prefer_installed_dependencies(requirements_path)
            except Exception as exc:
                logger.info("插件 %s 预加载已安装依赖失败: %s", root_dir_name, exc)
        try:
            return module_importer(path, fromlist=[module_str])
        except ModuleNotFoundError as import_exc:
            if recovery_state.mode in {
                ImportDependencyRecoveryMode.PRELOAD_AND_RECOVER,
                ImportDependencyRecoveryMode.RECOVER_ON_FAILURE,
            }:
                recovered_module = self._try_import_from_installed_dependencies(
                    path=path,
                    module_str=module_str,
                    root_dir_name=root_dir_name,
                    requirements_path=requirements_path,
                    import_exc=import_exc,
                    module_importer=module_importer,
                )
                if recovered_module is not None:
                    return recovered_module
            elif (
                recovery_state.mode is ImportDependencyRecoveryMode.REINSTALL_ON_FAILURE
            ):
                assert recovery_state.install_plan is not None
                logger.info(
                    "插件 %s 预检查检测到版本不匹配，跳过已安装依赖恢复: %s",
                    root_dir_name,
                    sorted(recovery_state.install_plan.version_mismatch_names),
                )
            plugin_dir_path = os.path.dirname(requirements_path)
            await self._packages.ensure_requirements(plugin_dir_path, root_dir_name)
            return module_importer(path, fromlist=[module_str])

    @staticmethod
    def related_modules(plugin_root_dir: str, *, reserved: bool) -> list[str]:
        """Return all imported Python modules owned by one plugin package."""
        namespace = "astrbot.builtin_stars" if reserved else "data.plugins"
        module_prefix = f"{namespace}.{plugin_root_dir}"
        return [
            key
            for key in list(sys.modules)
            if PluginCatalog.is_plugin_module_path(key, module_prefix)
        ]

    def purge_modules(
        self,
        *,
        module_patterns: list[str] | None = None,
        root_dir_name: str | None = None,
        reserved: bool = False,
    ) -> None:
        """Remove only modules owned by a plugin package from ``sys.modules``."""
        if module_patterns:
            for pattern in module_patterns:
                for key in list(sys.modules):
                    if key.startswith(pattern):
                        del sys.modules[key]
                        logger.debug("删除模块 %s", key)
        if root_dir_name:
            for module_name in self.related_modules(root_dir_name, reserved=reserved):
                sys.modules.pop(module_name, None)

    def cleanup_failed_package(self, dir_name: str, *, reserved: bool = False) -> None:
        """Roll back all published state left by a failed plugin import/load."""
        self.purge_modules(root_dir_name=dir_name, reserved=reserved)
        for metadata in self._catalog.cleanup_failed_package(
            dir_name, reserved=reserved
        ):
            self._extensions.rollback_metadata(metadata)

    def unpublish_plugin(self, plugin_module_path: str) -> StarMetadata | None:
        """Remove one live plugin's declarations and imported package modules."""
        metadata = self._catalog.unpublish(plugin_module_path)
        if metadata is not None:
            self.purge_modules(
                root_dir_name=metadata.root_dir_name,
                reserved=metadata.reserved,
            )
        return metadata

    def _build_failed_plugin_record(
        self,
        *,
        root_dir_name: str,
        plugin_dir_path: str,
        reserved: bool,
        error: BaseException | str,
        error_trace: str,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "name": root_dir_name,
            "error": str(error),
            "traceback": error_trace,
            "reserved": reserved,
        }
        try:
            metadata = self.load_metadata(plugin_path=plugin_dir_path)
            record.update(
                {
                    "name": metadata.name,
                    "author": metadata.author,
                    "desc": metadata.desc,
                    "short_desc": metadata.short_desc,
                    "version": metadata.version,
                    "repo": metadata.repo,
                    "display_name": metadata.display_name,
                    "support_platforms": metadata.support_platforms,
                    "astrbot_version": metadata.astrbot_version,
                },
            )
        except Exception as metadata_error:
            logger.debug(
                "读取失败插件 %s 元数据失败: %s", root_dir_name, metadata_error
            )
        return record

    def _rebuild_failed_plugin_info(self) -> None:
        if not self._failed_plugins:
            self._failed_plugin_info = ""
            return
        lines = []
        for dir_name, info in self._failed_plugins.items():
            error = info.get("error", "未知错误")
            display_name = info.get("display_name") or info.get("name") or dir_name
            version = info.get("version") or info.get("astrbot_version")
            if version:
                lines.append(
                    f"加载插件「{display_name}」(目录: {dir_name}, 版本: {version}) 时出现问题，原因：{error}。",
                )
            else:
                lines.append(
                    f"加载插件「{display_name}」(目录: {dir_name}) 时出现问题，原因：{error}。"
                )
        self._failed_plugin_info = "\n".join(lines) + "\n"

    def record_failed_install(
        self,
        *,
        dir_name: str,
        plugin_path: str,
        error: Exception,
    ) -> None:
        """Record a failed staged installation without publishing it as a plugin."""
        if (
            not dir_name
            or not plugin_path
            or not os.path.isdir(plugin_path)
            or dir_name in self._failed_plugins
            or self._catalog.plugins.get_by_name(dir_name) is not None
        ):
            return
        if any(
            plugin.root_dir_name == dir_name for plugin in self._catalog.plugins.all()
        ):
            return
        self._failed_plugins[dir_name] = self._build_failed_plugin_record(
            root_dir_name=dir_name,
            plugin_dir_path=plugin_path,
            reserved=False,
            error=error,
            error_trace=traceback.format_exc(),
        )
        self._rebuild_failed_plugin_info()

    async def _load_preferences(self) -> tuple[list, list, dict]:
        return (
            await self._preferences.global_get("inactivated_plugins", []),
            await self._preferences.global_get("inactivated_llm_tools", []),
            await self._preferences.global_get("alter_cmd", {}),
        )

    def _apply_plugin_metadata(
        self,
        metadata: StarMetadata,
        plugin_dir_path: str,
        plugin_config: AstrBotConfig | None,
        *,
        ignore_version_check: bool,
        metadata_yaml: StarMetadata,
    ) -> tuple[str, str, str]:
        metadata.name = metadata_yaml.name
        metadata.author = metadata_yaml.author
        metadata.desc = metadata_yaml.desc
        metadata.short_desc = metadata_yaml.short_desc
        metadata.version = metadata_yaml.version
        metadata.repo = metadata_yaml.repo
        metadata.display_name = metadata_yaml.display_name
        metadata.support_platforms = metadata_yaml.support_platforms
        metadata.astrbot_version = metadata_yaml.astrbot_version
        metadata.dashboard = metadata_yaml.dashboard
        metadata.dashboard_root = metadata_yaml.dashboard_root
        metadata.i18n = metadata_yaml.i18n
        metadata.authorization_actions = metadata_yaml.authorization_actions
        if not ignore_version_check:
            is_valid, error_message = self.validate_astrbot_version_specifier(
                metadata.astrbot_version,
            )
            if not is_valid:
                raise PluginVersionUnsupportedError(
                    error_message
                    or "The plugin does not support the current AstrBot version.",
                )
        metadata.config = plugin_config
        plugin_name = (metadata.name or "unknown").lower().replace("/", "_")
        plugin_author = (metadata.author or "unknown").lower().replace("/", "_")
        plugin_id = f"{plugin_author}/{plugin_name}"
        if metadata.star_cls_type:
            setattr(metadata.star_cls_type, "plugin_id", plugin_id)
        return plugin_name, plugin_author, plugin_id

    def _instantiate_plugin(
        self,
        metadata: StarMetadata,
        plugin_config: AstrBotConfig | None,
        plugin_name: str,
        plugin_author: str,
        plugin_id: str,
    ) -> None:
        del plugin_name, plugin_author
        if metadata.star_cls_type is None:
            return
        if plugin_config:
            metadata.star_cls = metadata.star_cls_type(
                context=self._plugin_context.for_plugin(
                    metadata.plugin_id,
                    metadata.authorization_actions,
                    allow_core_actions=metadata.reserved,
                ),
                config=plugin_config,
            )
        else:
            metadata.star_cls = metadata.star_cls_type(
                context=self._plugin_context.for_plugin(
                    metadata.plugin_id,
                    metadata.authorization_actions,
                    allow_core_actions=metadata.reserved,
                )
            )
        if metadata.star_cls:
            setattr(metadata.star_cls, "plugin_id", plugin_id)

    def bind_handlers(
        self,
        metadata: StarMetadata,
        inactivated_llm_tools: list,
    ) -> None:
        """Bind declared handlers/tools to the newly constructed Star instance."""
        assert metadata.module_path is not None
        plugin_disabled = metadata.star_cls is None
        catalogs = self._catalog.runtime_catalogs
        for handler in catalogs.handlers.get_handlers_by_module_name(
            metadata.module_path
        ):
            raw_handler = (
                handler.handler.func
                if isinstance(handler.handler, functools.partial)
                else handler.handler
            )
            handler.handler = raw_handler
            if not plugin_disabled and metadata.star_cls is not None:
                handler.handler = functools.partial(raw_handler, metadata.star_cls)

        for func_tool in catalogs.tools.func_list:
            tools = list(self._catalog.iter_tool_tree(func_tool))
            for tool in tools:
                if tool.handler_module_path != metadata.module_path:
                    continue
                raw_handler = (
                    tool.handler.func
                    if isinstance(tool.handler, functools.partial)
                    else tool.handler
                )
                tool.handler = raw_handler
                tool.active = not plugin_disabled
                if (
                    raw_handler is not None
                    and not plugin_disabled
                    and metadata.star_cls
                ):
                    tool.handler = functools.partial(raw_handler, metadata.star_cls)
                if tool.name in inactivated_llm_tools:
                    tool.active = False

    def _apply_plugin_handler_permissions(
        self,
        metadata: StarMetadata,
        alter_cmd: dict,
    ) -> list[str]:
        assert metadata.module_path is not None
        full_names: list[str] = []
        plugin_cfg = alter_cmd.setdefault(metadata.name, {})
        for (
            handler
        ) in self._catalog.runtime_catalogs.handlers.get_handlers_by_module_name(
            metadata.module_path,
        ):
            full_names.append(handler.handler_full_name)
            command_id = command_id_for_handler(metadata.name or "", handler)
            command = take_alter_cmd_entry(plugin_cfg, command_id)
            configured_action = (
                command.get("permission_action") if isinstance(command, dict) else None
            )
            if isinstance(configured_action, str) and configured_action:
                action = self._resolve_plugin_action(metadata, configured_action)
                for filter_ in handler.event_filters:
                    if isinstance(filter_, ActionPermissionFilter):
                        filter_.action = action
                        break
                else:
                    handler.event_filters.append(ActionPermissionFilter(action))
                logger.debug(
                    "插入权限过滤器 %s 到 %s 的 %s 方法。",
                    action,
                    metadata.name,
                    handler.handler_name,
                )

            permission_filters = [
                filter_
                for filter_ in handler.event_filters
                if isinstance(filter_, ActionPermissionFilter)
            ]
            for filter_ in permission_filters:
                filter_.action = self._resolve_plugin_action(metadata, filter_.action)
            if (
                not metadata.reserved
                and handler.event_type is EventType.AdapterMessageEvent
                and not permission_filters
            ):
                # Plugin message handlers execute with user-originated events.
                # Without an explicit action they have no policy boundary, so
                # bind an intentionally invalid action and fail closed.
                handler.event_filters.append(
                    ActionPermissionFilter("plugin:__undeclared__")
                )
                logger.warning(
                    "Plugin handler %s has no declared authorization action; denying it.",
                    handler.handler_full_name,
                )
        return full_names

    @staticmethod
    def _resolve_plugin_action(metadata: StarMetadata, action: str) -> str:
        """Expand and validate plugin-local action declarations."""

        if not action.startswith("plugin:"):
            return action
        local_action = action.removeprefix("plugin:")
        prefix = f"plugin:{metadata.plugin_id}:"
        resolved_action = (
            f"{prefix}{local_action}" if ":" not in local_action else action
        )
        if (
            not resolved_action.startswith(prefix)
            or resolved_action not in metadata.authorization_actions
        ):
            raise ValueError(
                f"Plugin handler action is not declared: {resolved_action!r}"
            )
        return resolved_action

    async def _initialize_plugin_and_run_hooks(self, metadata: StarMetadata) -> None:
        await self._extensions.initialize(metadata)
        for (
            handler
        ) in self._catalog.runtime_catalogs.handlers.get_handlers_by_event_type(
            EventType.OnPluginLoadedEvent,
        ):
            try:
                source_plugin = self._catalog.plugins.get_by_module(
                    handler.handler_module_path,
                )
                logger.info(
                    "hook(on_plugin_loaded) -> %s - %s",
                    source_plugin.name if source_plugin else "unknown",
                    handler.handler_name,
                )
                await handler.handler(metadata)
            except Exception:
                logger.error(traceback.format_exc())

    async def load(
        self,
        *,
        specified_module_path: str | None = None,
        specified_dir_name: str | None = None,
        ignore_version_check: bool = False,
        sync_command_configs_after_load: bool = True,
    ) -> tuple[bool, str | None]:
        """Discover candidate packages and load each selected module.

        Args:
            specified_module_path: Optional exact plugin entry module.
            specified_dir_name: Optional exact plugin package directory.
            ignore_version_check: Whether to bypass plugin version validation.
            sync_command_configs_after_load: Whether to synchronize the
                shared command store after publication. Staged reloads disable
                this until their isolated declarations are promoted.
        """
        plugin_modules = self.discover_modules()
        if not plugin_modules:
            return False, "未找到任何插件模块"
        (
            inactivated_plugins,
            inactivated_llm_tools,
            alter_cmd,
        ) = await self._load_preferences()
        return await self._load_modules(
            plugin_modules,
            inactivated_plugins,
            inactivated_llm_tools,
            alter_cmd,
            specified_module_path=specified_module_path,
            specified_dir_name=specified_dir_name,
            ignore_version_check=ignore_version_check,
            sync_command_configs_after_load=sync_command_configs_after_load,
        )

    async def _load_modules(
        self,
        plugin_modules: list[PluginModuleEntry],
        inactivated_plugins: list,
        inactivated_llm_tools: list,
        alter_cmd: dict,
        *,
        specified_module_path: str | None,
        specified_dir_name: str | None,
        ignore_version_check: bool,
        sync_command_configs_after_load: bool,
    ) -> tuple[bool, str | None]:
        has_load_error = False
        for plugin_module in plugin_modules:
            root_dir_name = str(plugin_module["pname"])
            reserved = bool(plugin_module.get("reserved", False))
            plugin_dir_path = (
                os.path.join(self._reserved_plugin_path, root_dir_name)
                if reserved
                else os.path.join(self._plugin_store_path, root_dir_name)
            )
            try:
                module_str = str(plugin_module["module"])
                requirements_path = os.path.join(plugin_dir_path, "requirements.txt")
                module_path = (
                    ("astrbot.builtin_stars." if reserved else "data.plugins.")
                    + root_dir_name
                    + "."
                    + module_str
                )
                if specified_module_path and module_path != specified_module_path:
                    continue
                if specified_dir_name and root_dir_name != specified_dir_name:
                    continue

                logger.info("Loading plugin %s ...", root_dir_name)
                validated_metadata = self.load_metadata(plugin_path=plugin_dir_path)
                try:
                    module = await self.import_with_dependency_recovery(
                        path=module_path,
                        module_str=module_str,
                        root_dir_name=root_dir_name,
                        requirements_path=requirements_path,
                        reserved=reserved,
                    )
                except Exception as exc:
                    error_trace = traceback.format_exc()
                    logger.error(error_trace)
                    logger.error("插件 %s 导入失败。原因：%s", root_dir_name, exc)
                    has_load_error = True
                    self._failed_plugins[root_dir_name] = (
                        self._build_failed_plugin_record(
                            root_dir_name=root_dir_name,
                            plugin_dir_path=plugin_dir_path,
                            reserved=reserved,
                            error=exc,
                            error_trace=error_trace,
                        )
                    )
                    self.cleanup_failed_package(root_dir_name, reserved=reserved)
                    continue

                plugin_config = None
                schema_path = os.path.join(plugin_dir_path, "_conf_schema.json")
                if os.path.exists(schema_path):
                    with open(schema_path, encoding="utf-8-sig") as handle:
                        plugin_config = AstrBotConfig(
                            config_path=os.path.join(
                                self._plugin_config_path,
                                f"{root_dir_name}_config.json",
                            ),
                            schema=json.loads(handle.read()),
                        )
                logo_path = os.path.join(plugin_dir_path, "logo.png")
                if self._catalog.plugins.get_by_module(module_path) is not None:
                    logger.warning(
                        "Plugin %s is already loaded; keeping its existing runtime.",
                        root_dir_name,
                    )
                    continue
                declaration = collect_star_declaration(module)
                if declaration is None:
                    raise Exception(
                        f"插件 {root_dir_name} 未声明 Star 类。"
                        "请确保 main.py 中存在继承自 Star 的插件主类。",
                    )
                if declaration.module_path != module_path:
                    raise ValueError(
                        "Plugin Star declaration must belong to its entry module: "
                        f"{declaration.module_path!r}",
                    )
                metadata = StarMetadata(
                    star_cls_type=declaration.star_cls_type,
                    module_path=declaration.module_path,
                    module=module,
                    root_dir_name=root_dir_name,
                    reserved=reserved,
                    activated=module_path not in inactivated_plugins,
                )
                plugin_name, plugin_author, plugin_id = self._apply_plugin_metadata(
                    metadata,
                    plugin_dir_path,
                    plugin_config,
                    ignore_version_check=ignore_version_check,
                    metadata_yaml=validated_metadata,
                )
                declarations = collect_plugin_module_declarations(module)
                self._catalog.materialize_declarations(
                    metadata, declaration, declarations
                )
                self._catalog.register_adapter_descriptors(
                    self._catalog.module_prefix(metadata)
                )
                self._catalog.publish_plugin(metadata)
                if metadata.activated:
                    self._instantiate_plugin(
                        metadata,
                        plugin_config,
                        plugin_name,
                        plugin_author,
                        plugin_id,
                    )
                else:
                    metadata.star_cls = None
                    logger.info("Plugin %s is disabled.", metadata.name)
                self.bind_handlers(metadata, inactivated_llm_tools)
                if os.path.exists(logo_path):
                    metadata.logo_path = logo_path
                metadata.star_handler_full_names = (
                    self._apply_plugin_handler_permissions(
                        metadata,
                        alter_cmd,
                    )
                )
                if self._after_module_materialized is not None:
                    self._after_module_materialized()
                await self._initialize_plugin_and_run_hooks(metadata)
            except Exception as exc:
                logger.error("----- 插件 %s 载入失败 -----", root_dir_name)
                errors = traceback.format_exc()
                for line in errors.split("\n"):
                    logger.error("| %s", line)
                logger.error("----------------------------------")
                has_load_error = True
                self._failed_plugins[root_dir_name] = self._build_failed_plugin_record(
                    root_dir_name=root_dir_name,
                    plugin_dir_path=plugin_dir_path,
                    reserved=reserved,
                    error=exc,
                    error_trace=errors,
                )
                self.cleanup_failed_package(root_dir_name, reserved=reserved)

        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        if sync_command_configs_after_load:
            await self.sync_command_configs()
        await self._preferences.global_put("alter_cmd", alter_cmd)
        self._rebuild_failed_plugin_info()
        return (False, self._failed_plugin_info) if has_load_error else (True, None)

    async def sync_command_configs(self) -> None:
        """Synchronize persisted command state for this loader's catalog."""
        try:
            await sync_command_configs(
                self._execution_context.database,
                self._catalog.runtime_catalogs.handlers,
            )
        except Exception as exc:
            logger.error("同步指令配置失败: %s", exc)
            logger.error(traceback.format_exc())

    def remove_failed_plugin(self, dir_name: str) -> None:
        """Forget a failure record after successful reload or uninstall."""
        self._failed_plugins.pop(dir_name, None)
        self._rebuild_failed_plugin_info()
