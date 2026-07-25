"""Lifecycle ownership for loaded plugin runtimes."""

from __future__ import annotations

import asyncio
import copy
import os
import sys
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from astrbot import logger
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.utils.io import remove_dir
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.core.utils.task_utils import cancel_tracked_tasks, create_tracked_task

from .dashboard_extension import DashboardExtensionAccess, DashboardExtensionRegistry
from .error_messages import format_plugin_error
from .plugin_catalog import PluginCatalog, PluginPackageSnapshot
from .plugin_context import PluginContext
from .plugin_extension_coordinator import PluginExtensionCoordinator
from .plugin_package_installer import PluginPackageInstaller
from .plugin_runtime_loader import PluginRuntimeLoader
from .star import StarMetadata
from .star_handler import EventType

try:
    from watchfiles import PythonFilter, awatch
except ImportError:
    PythonFilter = None
    awatch = None


_MISSING = object()


class _StagedModuleCache:
    """Keep reload imports private until their generation is promoted.

    Python owns one process-wide ``sys.modules`` mapping, so a full isolated
    import is not available for ordinary plugin packages. This helper narrows
    the unavoidable cache swap to synchronous import/materialization only. It
    restores the old generation before staged ``initialize()`` can await and
    installs the replacement map only as part of the short publish mutation.
    """

    __slots__ = (
        "_namespace",
        "_root_dir_name",
        "_original_modules",
        "_parent_package",
        "_parent_attribute",
        "_active",
        "staged_modules",
    )

    def __init__(
        self,
        *,
        root_dir_name: str,
        reserved: bool,
        original_modules: dict[str, ModuleType],
        parent_package: ModuleType | None,
        parent_attribute: object,
    ) -> None:
        self._namespace = "astrbot.builtin_stars" if reserved else "data.plugins"
        self._root_dir_name = root_dir_name
        self._original_modules = original_modules
        self._parent_package = parent_package
        self._parent_attribute = parent_attribute
        self._active = False
        self.staged_modules: dict[str, ModuleType] = {}

    @property
    def _prefix(self) -> str:
        return f"{self._namespace}.{self._root_dir_name}"

    def _related_module_names(self) -> tuple[str, ...]:
        prefix = self._prefix
        return tuple(
            module_name
            for module_name in sys.modules
            if module_name == prefix or module_name.startswith(f"{prefix}.")
        )

    def _set_parent_attribute(self, modules: dict[str, ModuleType]) -> None:
        if self._parent_package is None:
            return
        package_module = modules.get(self._prefix)
        if package_module is not None:
            setattr(self._parent_package, self._root_dir_name, package_module)
        elif self._parent_attribute is _MISSING:
            self._parent_package.__dict__.pop(self._root_dir_name, None)
        else:
            setattr(self._parent_package, self._root_dir_name, self._parent_attribute)

    def _replace_modules(self, modules: dict[str, ModuleType]) -> None:
        for module_name in self._related_module_names():
            sys.modules.pop(module_name, None)
        sys.modules.update(modules)
        self._set_parent_attribute(modules)

    def import_module(self, *args: Any, **kwargs: Any) -> ModuleType:
        """Import through a short-lived canonical-name cache substitution."""
        if self._active:
            raise RuntimeError("A staged plugin import is already active")
        self._replace_modules({})
        self._active = True
        try:
            return __import__(*args, **kwargs)
        except BaseException:
            self.restore_original_modules()
            raise

    def capture_staged_modules(self) -> None:
        """Retain the imported generation and immediately restore the live one."""
        if not self._active:
            return
        self.staged_modules = {
            module_name: sys.modules[module_name]
            for module_name in self._related_module_names()
            if isinstance(sys.modules.get(module_name), ModuleType)
        }
        self.restore_original_modules()

    def restore_original_modules(self) -> None:
        """Restore the live generation after a stage attempt or rollback."""
        self._replace_modules(self._original_modules)
        self._active = False

    def promote(self) -> None:
        """Publish the captured staged module objects synchronously."""
        if self._active:
            self.capture_staged_modules()
        self._replace_modules(self.staged_modules)

    def discard(self) -> None:
        """Release unpublished module references while retaining live imports."""
        self.restore_original_modules()
        self.staged_modules.clear()


@dataclass(slots=True)
class _StagedPlugin:
    """A fully initialized plugin generation not yet visible to the runtime."""

    metadata: StarMetadata
    catalog: PluginCatalog
    extensions: PluginExtensionCoordinator
    execution_context: Any
    plugin_context: PluginContext
    loader: PluginRuntimeLoader
    module_cache: _StagedModuleCache


@dataclass(slots=True)
class _PromotionJournalEntry:
    """One replacement committed during an all-plugin reload transaction."""

    staged: _StagedPlugin
    previous: PluginPackageSnapshot
    extensions_promoted: bool = False


class PluginLifecycle:
    """Coordinate live plugin mutations under one instance-owned lock."""

    def __init__(
        self,
        *,
        refresh_platform_commands: Callable[[], Awaitable[None]],
        catalog: PluginCatalog,
        loader: PluginRuntimeLoader,
        packages: PluginPackageInstaller,
        extensions: PluginExtensionCoordinator,
        preferences: SharedPreferences,
        plugin_store_path: str,
        reserved_plugin_path: str,
        background_tasks: set[asyncio.Task[Any]],
    ) -> None:
        self._refresh_platform_commands = refresh_platform_commands
        self._catalog = catalog
        self._loader = loader
        self._packages = packages
        self._extensions = extensions
        self._preferences = preferences
        self._plugin_store_path = plugin_store_path
        self._reserved_plugin_path = reserved_plugin_path
        self._lock = asyncio.Lock()
        self._background_tasks = background_tasks
        self._watch_started = False

    def start(self) -> None:
        """Start optional plugin-file monitoring after full composition."""
        if self._watch_started or os.getenv("ASTRBOT_RELOAD", "0") != "1":
            return
        if awatch is None or PythonFilter is None:
            logger.warning("未安装 watchfiles，无法实现插件的热重载。")
            return
        self._watch_started = True
        create_tracked_task(
            self._background_tasks,
            self._watch_plugin_changes(),
            name="plugin-watch",
        )

    async def stop(self) -> None:
        """Cancel lifecycle-owned watcher and metric tasks exactly once."""
        self._watch_started = False
        await cancel_tracked_tasks(self._background_tasks)

    async def _refresh_command_surfaces(self) -> None:
        self._catalog.refresh_command_catalogs()
        await self._refresh_platform_commands()

    async def load(
        self,
        *,
        specified_module_path: str | None = None,
        specified_dir_name: str | None = None,
        ignore_version_check: bool = False,
    ) -> tuple[bool, str | None]:
        """Load selected plugins and refresh the command-facing runtime."""
        async with self._lock:
            return await self._load_unlocked(
                specified_module_path=specified_module_path,
                specified_dir_name=specified_dir_name,
                ignore_version_check=ignore_version_check,
            )

    async def _load_unlocked(
        self,
        *,
        specified_module_path: str | None = None,
        specified_dir_name: str | None = None,
        ignore_version_check: bool = False,
    ) -> tuple[bool, str | None]:
        result = await self._loader.load(
            specified_module_path=specified_module_path,
            specified_dir_name=specified_dir_name,
            ignore_version_check=ignore_version_check,
        )
        await self._refresh_command_surfaces()
        return result

    async def reload_failed_plugin(self, dir_name: str) -> tuple[bool, str | None]:
        """Retry a failed user plugin from its recorded directory."""
        async with self._lock:
            if self._loader.failed_plugin(dir_name) is None:
                return False, "插件不存在于失败列表中"
            self._loader.cleanup_failed_package(dir_name)
            plugin_path = os.path.join(self._plugin_store_path, dir_name)
            await self._packages.ensure_requirements(plugin_path, dir_name)
            success, error = await self._load_unlocked(specified_dir_name=dir_name)
            if success:
                self._loader.remove_failed_plugin(dir_name)
                return True, None
            return False, error

    async def reload(
        self,
        specified_plugin_name: str | None = None,
    ) -> tuple[bool, str | None]:
        """Terminate, unpublish, and load one plugin or the complete set."""
        async with self._lock:
            return await self._reload_unlocked(specified_plugin_name)

    async def _reload_unlocked(
        self,
        specified_plugin_name: str | None = None,
    ) -> tuple[bool, str | None]:
        """Stage and promote replacement plugin generations.

        The old generation deliberately remains published while the new
        package is imported and initialized in isolated catalogs.  This keeps
        active handlers, tools, adapter descriptors, and Dashboard extension
        actions available if the replacement fails to load.
        """
        selected: list[StarMetadata]
        if specified_plugin_name is None:
            selected = list(self._catalog.plugins.all())
        else:
            plugin = self._catalog.plugins.get_by_name(specified_plugin_name)
            selected = [plugin] if plugin is not None else []

        if not selected:
            # Preserve the established behavior for an unknown name: perform
            # regular discovery rather than silently treating it as success.
            return await self._load_unlocked()

        staged_generations: list[_StagedPlugin] = []
        promotion_journal: list[_PromotionJournalEntry] = []
        try:
            for metadata in selected:
                staged, error = await self._stage_reload_generation(metadata)
                if staged is None:
                    await self._discard_staged_generations(staged_generations)
                    return False, error
                staged_generations.append(staged)

            # Every catalog and extension collision is preflighted before an
            # active generation is touched. This makes the following mutation
            # sequence a journaled transaction instead of a series of
            # independently visible reloads.
            self._validate_staged_generations(selected, staged_generations)

            for staged in staged_generations:
                current = self._catalog.plugins.get_by_module(
                    staged.metadata.module_path
                )
                if current is None:
                    raise RuntimeError(
                        "Plugin disappeared while its reload generation was staged",
                    )
                previous = self._catalog.snapshot_package(current)
                try:
                    self._catalog.promote_staged_package(
                        current,
                        staged.catalog,
                        staged.metadata,
                    )
                    self._promote_staged_modules(staged)
                    self._catalog.refresh_plugin_log_modules(staged.metadata)
                    self._promote_staged_context(staged)
                except BaseException:
                    self._catalog.restore_package(previous)
                    self._restore_staged_modules(staged)
                    self._catalog.refresh_plugin_log_modules(previous.metadata)
                    raise
                promotion_journal.append(
                    _PromotionJournalEntry(staged=staged, previous=previous),
                )

            await self._loader.sync_command_configs()
            await self._refresh_command_surfaces()

            for entry in promotion_journal:
                current = entry.previous.metadata
                await self._extensions.promote_staged_generation(
                    entry.staged.extensions,
                    current,
                    entry.staged.metadata,
                    reason="reload",
                )
                entry.extensions_promoted = True

            for entry in promotion_journal:
                try:
                    await self.terminate_plugin(entry.previous.metadata)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(traceback.format_exc())
                    logger.warning(
                        "插件 %s 未被正常终止: %s, 可能会导致该插件运行不正常。",
                        entry.previous.metadata.name,
                        exc,
                    )
            return True, None
        except asyncio.CancelledError:
            await self._rollback_promotions(promotion_journal)
            await self._discard_staged_generations(staged_generations)
            raise
        except Exception as exc:
            await self._rollback_promotions(promotion_journal)
            await self._discard_staged_generations(staged_generations)
            logger.error("插件热重载 staging/promotion 失败: %s", exc, exc_info=True)
            return False, str(exc)

    @staticmethod
    def _metadata_for_staged_path(
        selected: list[StarMetadata],
        staged_metadata: StarMetadata,
    ) -> StarMetadata:
        """Find the original metadata for a staged entry module."""
        for metadata in selected:
            if metadata.module_path == staged_metadata.module_path:
                return metadata
        raise RuntimeError(
            f"No live plugin generation for {staged_metadata.module_path!r}",
        )

    def _validate_staged_generations(
        self,
        selected: list[StarMetadata],
        staged_generations: list[_StagedPlugin],
    ) -> None:
        """Preflight live and cross-stage declaration collisions."""
        seen_providers: dict[str, str] = {}
        seen_platforms: dict[str, str] = {}
        seen_handlers: dict[str, str] = {}
        seen_tools: dict[str, str] = {}
        seen_extension_ids: dict[str, str] = {}

        def require_unique(
            seen: dict[str, str],
            value: str,
            module_path: str,
            label: str,
        ) -> None:
            previous = seen.setdefault(value, module_path)
            if previous != module_path:
                raise ValueError(
                    f"{label} collision between staged plugins: {value!r}",
                )

        for staged in staged_generations:
            current = self._catalog.plugins.get_by_module(
                staged.metadata.module_path,
            ) or self._metadata_for_staged_path(selected, staged.metadata)
            self._catalog.validate_staged_package(
                current,
                staged.catalog,
                staged.metadata,
            )
            self._extensions.validate_staged_generation(
                staged.extensions,
                current,
                staged.metadata,
            )

            module_path = staged.metadata.module_path or ""
            for (
                registration
            ) in staged.catalog.runtime_catalogs.providers.registrations():
                require_unique(
                    seen_providers,
                    registration.descriptor.type,
                    module_path,
                    "Provider adapter type",
                )
            for (
                registration
            ) in staged.catalog.runtime_catalogs.platforms.registrations():
                require_unique(
                    seen_platforms,
                    registration.descriptor.name,
                    module_path,
                    "Platform adapter name",
                )
            for handler in staged.catalog.runtime_catalogs.handlers:
                require_unique(
                    seen_handlers,
                    handler.handler_full_name,
                    module_path,
                    "Handler",
                )
            for tool in staged.catalog.runtime_catalogs.tools.func_list:
                require_unique(seen_tools, tool.name, module_path, "Tool name")
            for extension in staged.extensions.registry.snapshots():
                require_unique(
                    seen_extension_ids,
                    extension.extension_id,
                    module_path,
                    "Dashboard extension ID",
                )

    async def _rollback_promotions(
        self,
        promotion_journal: list[_PromotionJournalEntry],
    ) -> None:
        """Restore all already-published generations after batch failure."""
        for entry in reversed(promotion_journal):
            try:
                if entry.extensions_promoted:
                    await self._extensions.deactivate(
                        entry.staged.metadata,
                        reason="reload_rollback",
                        release=True,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error(
                    "Failed to deactivate promoted plugin %s during rollback",
                    entry.previous.metadata.name,
                    exc_info=True,
                )
        # Restore catalog declarations in original promotion order. Handler and
        # tool registries preserve stable ordering for equal priorities, so a
        # reverse restore would visibly reorder unrelated plugin commands.
        for entry in promotion_journal:
            try:
                self._catalog.restore_package(entry.previous)
                self._restore_staged_modules(entry.staged)
                self._catalog.refresh_plugin_log_modules(entry.previous.metadata)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error(
                    "Failed to restore promoted plugin %s during rollback",
                    entry.previous.metadata.name,
                    exc_info=True,
                )
        for entry in promotion_journal:
            if not entry.extensions_promoted:
                continue
            try:
                await self._extensions.initialize(entry.previous.metadata)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error(
                    "Failed to restore Dashboard extension for plugin %s",
                    entry.previous.metadata.name,
                    exc_info=True,
                )
        if promotion_journal:
            try:
                await self._refresh_command_surfaces()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error(
                    "Failed to refresh command surfaces after plugin rollback",
                    exc_info=True,
                )

    @staticmethod
    def _promote_staged_modules(staged: _StagedPlugin) -> None:
        module_cache = getattr(staged, "module_cache", None)
        if isinstance(module_cache, _StagedModuleCache):
            module_cache.promote()

    @staticmethod
    def _restore_staged_modules(staged: _StagedPlugin) -> None:
        module_cache = getattr(staged, "module_cache", None)
        if isinstance(module_cache, _StagedModuleCache):
            module_cache.restore_original_modules()

    async def _stage_reload_generation(
        self,
        current: StarMetadata,
    ) -> tuple[_StagedPlugin | None, str | None]:
        """Build a replacement generation without mutating the live catalog."""
        module_path = current.module_path
        root_dir_name = current.root_dir_name
        if not module_path or not root_dir_name:
            return None, "插件缺少重载所需的模块路径或根目录信息"

        namespace = "astrbot.builtin_stars" if current.reserved else "data.plugins"
        parent_package = sys.modules.get(namespace)
        parent_attribute = (
            getattr(parent_package, root_dir_name, _MISSING)
            if isinstance(parent_package, ModuleType)
            else _MISSING
        )
        original_modules = {
            name: sys.modules[name]
            for name in self._loader.related_modules(
                root_dir_name,
                reserved=current.reserved,
            )
            if isinstance(sys.modules.get(name), ModuleType)
        }
        module_cache = _StagedModuleCache(
            root_dir_name=root_dir_name,
            reserved=current.reserved,
            original_modules=original_modules,
            parent_package=(
                parent_package if isinstance(parent_package, ModuleType) else None
            ),
            parent_attribute=parent_attribute,
        )

        staging_catalogs = RuntimeCatalogs()
        staging_registry = DashboardExtensionRegistry()
        staging_extensions = PluginExtensionCoordinator(staging_registry)
        staging_execution_context = copy.copy(self._loader._execution_context)
        staging_execution_context.catalogs = staging_catalogs
        # ``copy.copy`` is only appropriate for the immutable/shared service
        # ports. These containers receive registrations or task ownership and
        # must never be shared with the published execution context.
        staging_execution_context._register_tasks = []
        staging_execution_context.background_tasks = set()
        staging_execution_context._star_manager = None
        staging_execution_context.dashboard_extension_registry = staging_registry
        staging_execution_context.dashboard_extensions = DashboardExtensionAccess(
            staging_registry,
        )
        staging_context = PluginContext.from_execution_context(
            staging_execution_context,
        )
        staging_context._bind_plugin_lifecycle_control(self)
        staging_catalog = PluginCatalog(staging_catalogs, live_logging=False)
        staging_loader = PluginRuntimeLoader(
            execution_context=staging_execution_context,
            catalog=staging_catalog,
            extensions=staging_extensions,
            plugin_context=staging_context,
            preferences=self._preferences,
            packages=self._packages,
            plugin_store_path=self._plugin_store_path,
            plugin_config_path=self._loader._plugin_config_path,
            reserved_plugin_path=self._reserved_plugin_path,
            module_importer=module_cache.import_module,
            after_module_materialized=module_cache.capture_staged_modules,
        )

        try:
            success, error = await staging_loader.load(
                specified_module_path=module_path,
                specified_dir_name=root_dir_name,
                sync_command_configs_after_load=False,
            )
            replacement = staging_catalog.plugins.get_by_module(module_path)
            if not success or replacement is None:
                await self._discard_staged_generation(
                    catalog=staging_catalog,
                    extensions=staging_extensions,
                    metadata=replacement,
                    root_dir_name=root_dir_name,
                    reserved=current.reserved,
                    execution_context=staging_execution_context,
                )
                return None, error or "插件重载 staging 未产生新的运行时"
            return (
                _StagedPlugin(
                    metadata=replacement,
                    catalog=staging_catalog,
                    extensions=staging_extensions,
                    execution_context=staging_execution_context,
                    plugin_context=staging_context,
                    loader=staging_loader,
                    module_cache=module_cache,
                ),
                None,
            )
        except asyncio.CancelledError:
            await self._discard_staged_generation(
                catalog=staging_catalog,
                extensions=staging_extensions,
                metadata=staging_catalog.plugins.get_by_module(module_path),
                root_dir_name=root_dir_name,
                reserved=current.reserved,
                execution_context=staging_execution_context,
            )
            raise
        except Exception as exc:
            await self._discard_staged_generation(
                catalog=staging_catalog,
                extensions=staging_extensions,
                metadata=staging_catalog.plugins.get_by_module(module_path),
                root_dir_name=root_dir_name,
                reserved=current.reserved,
                execution_context=staging_execution_context,
            )
            return None, str(exc)
        finally:
            # If materialization failed before the loader's hook ran, this
            # still restores the old generation before another coroutine can
            # observe the failed import cache.
            module_cache.restore_original_modules()

    async def _discard_staged_generations(
        self,
        staged_generations: list[_StagedPlugin],
    ) -> None:
        """Dispose unpromoted generations and restore their module objects."""
        for staged in reversed(staged_generations):
            current = self._catalog.plugins.get_by_module(staged.metadata.module_path)
            if current is staged.metadata:
                continue
            await self._discard_staged_generation(
                catalog=staged.catalog,
                extensions=staged.extensions,
                metadata=staged.metadata,
                root_dir_name=staged.metadata.root_dir_name or "",
                reserved=staged.metadata.reserved,
                execution_context=staged.execution_context,
            )
            module_cache = getattr(staged, "module_cache", None)
            if isinstance(module_cache, _StagedModuleCache):
                module_cache.discard()

    async def _discard_staged_generation(
        self,
        *,
        catalog: PluginCatalog,
        extensions: PluginExtensionCoordinator,
        metadata: StarMetadata | None,
        root_dir_name: str,
        reserved: bool,
        execution_context: Any | None = None,
    ) -> None:
        """Terminate one unpublished generation and remove its staging state."""
        if metadata is not None:
            try:
                await extensions.deactivate(
                    metadata,
                    reason="reload_rollback",
                    release=True,
                )
                instance = metadata.star_cls
                terminate = getattr(instance, "terminate", None)
                if callable(terminate):
                    result = terminate()
                    if isinstance(result, Awaitable):
                        await result
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Failed to terminate staged plugin %s during rollback",
                    metadata.name,
                    exc_info=True,
                )
        self._close_staged_registered_tasks(execution_context)
        background_tasks = getattr(execution_context, "background_tasks", None)
        if isinstance(background_tasks, set):
            await cancel_tracked_tasks(background_tasks)
        if root_dir_name:
            # A staging catalog is private, while the process module cache is
            # live. Do not call ``PluginRuntimeLoader.cleanup_failed_package``
            # here: it would purge the restored live generation.
            catalog.cleanup_failed_package(root_dir_name, reserved=reserved)
        else:
            # A malformed metadata object cannot be discovered by prefix, but
            # the temporary catalog is still private and safe to clear.
            catalog.runtime_catalogs.handlers.clear()
            catalog.runtime_catalogs.tools.func_list.clear()
            catalog.runtime_catalogs.plugins.clear()

    @staticmethod
    def _close_staged_registered_tasks(execution_context: Any | None) -> None:
        """Close deprecated staged task registrations instead of leaking them."""
        registered_tasks = getattr(execution_context, "_register_tasks", ())
        for task in registered_tasks:
            close = getattr(task, "close", None)
            if callable(close):
                close()
        if isinstance(registered_tasks, list):
            registered_tasks.clear()

    def _promote_staged_context(self, staged: _StagedPlugin) -> None:
        """Point retained plugin capability facades at the live runtime."""
        live_execution_context = self._loader._execution_context
        staged_tasks = getattr(staged.execution_context, "background_tasks", None)
        live_tasks = getattr(live_execution_context, "background_tasks", None)
        if isinstance(staged_tasks, set) and isinstance(live_tasks, set):
            live_tasks.update(staged_tasks)
            staged.execution_context.background_tasks = live_tasks
        self._close_staged_registered_tasks(staged.execution_context)
        staged.execution_context.catalogs = self._catalog.runtime_catalogs
        staged.execution_context.dashboard_extension_registry = (
            self._extensions.registry
        )
        staged.execution_context.dashboard_extensions = DashboardExtensionAccess(
            self._extensions.registry,
        )
        staged.plugin_context.dashboard_extensions = DashboardExtensionAccess(
            self._extensions.registry,
        )
        staged.plugin_context._rebind_runtime_catalogs(
            self._catalog.runtime_catalogs,
        )

    async def install_plugin(
        self,
        repo_url: str,
        proxy: str = "",
        ignore_version_check: bool = False,
        download_url: str = "",
    ) -> dict[str, str | None] | None:
        """Install a repository plugin through the package installer."""
        async with self._lock:
            return await self._packages.install_from_repository(
                repo_url=repo_url,
                proxy=proxy,
                ignore_version_check=ignore_version_check,
                download_url=download_url,
                loader=self._loader,
                load_plugin=self._load_unlocked,
            )

    async def install_plugin_from_file(
        self,
        zip_file_path: str,
        ignore_version_check: bool = False,
    ) -> dict[str, str | None] | None:
        """Install an uploaded plugin archive through the package installer."""
        async with self._lock:
            return await self._packages.install_from_file(
                zip_file_path=zip_file_path,
                ignore_version_check=ignore_version_check,
                loader=self._loader,
                load_plugin=self._load_unlocked,
            )

    async def update_plugin(
        self,
        plugin_name: str,
        proxy: str = "",
        download_url: str = "",
    ) -> None:
        """Update one non-bundled plugin under the lifecycle lock."""
        async with self._lock:
            await self._packages.update(
                plugin_name,
                proxy=proxy,
                download_url=download_url,
                loader=self._loader,
                reload_plugin=self._reload_unlocked,
            )

    async def uninstall_plugin(
        self,
        plugin_name: str,
        *,
        delete_config: bool = False,
        delete_data: bool = False,
    ) -> None:
        """Deactivate and remove one user plugin and optional artifacts."""
        async with self._lock:
            plugin = self._catalog.plugins.get_by_name(plugin_name)
            if plugin is None:
                raise Exception("插件不存在。")
            if plugin.reserved:
                raise Exception("该插件是 AstrBot 保留插件，无法卸载。")
            if plugin.module_path is None or plugin.root_dir_name is None:
                raise Exception(f"插件 {plugin_name} 数据不完整，无法卸载。")
            try:
                await self._extensions.deactivate(
                    plugin,
                    reason="uninstall",
                    release=True,
                )
                await self.terminate_plugin(plugin)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(traceback.format_exc())
                logger.warning(
                    "插件 %s 未被正常终止 %s, 可能会导致资源泄露等问题。",
                    plugin_name,
                    exc,
                )
            self._loader.unpublish_plugin(plugin.module_path)
            try:
                remove_dir(os.path.join(self._plugin_store_path, plugin.root_dir_name))
            except Exception as exc:
                raise Exception(
                    "移除插件成功，但是删除插件文件夹失败: "
                    f"{exc!s}。您可以手动删除该文件夹，位于 addons/plugins/ 下。",
                ) from exc
            await self._packages.cleanup_optional_artifacts(
                root_dir_name=plugin.root_dir_name,
                plugin_label=plugin_name,
                plugin_id=plugin.plugin_id,
                delete_config=delete_config,
                delete_data=delete_data,
            )
            await self._refresh_command_surfaces()

    async def uninstall_failed_plugin(
        self,
        dir_name: str,
        *,
        delete_config: bool = False,
        delete_data: bool = False,
    ) -> None:
        """Remove an unpublishable user plugin recorded by the loader."""
        async with self._lock:
            failed_info = self._loader.failed_plugin(dir_name)
            if failed_info is None:
                raise Exception(format_plugin_error("not_found_in_failed_list"))
            if failed_info.get("reserved"):
                raise Exception(format_plugin_error("reserved_plugin_cannot_uninstall"))
            self._loader.cleanup_failed_package(dir_name)
            plugin_path = os.path.join(self._plugin_store_path, dir_name)
            if os.path.exists(plugin_path):
                try:
                    remove_dir(plugin_path)
                except Exception as exc:
                    raise Exception(
                        format_plugin_error(
                            "failed_plugin_dir_remove_error",
                            error=f"{exc!s}",
                        ),
                    ) from exc
            else:
                logger.debug("插件目录不存在，继续清理失败记录: %s", plugin_path)
            plugin_label = (
                failed_info.get("display_name") or failed_info.get("name") or dir_name
            )
            await self._packages.cleanup_optional_artifacts(
                root_dir_name=dir_name,
                plugin_label=plugin_label,
                plugin_id=failed_info.get("plugin_id"),
                delete_config=delete_config,
                delete_data=delete_data,
            )
            self._loader.remove_failed_plugin(dir_name)

    async def turn_off_plugin(self, plugin_name: str) -> None:
        """Disable a live plugin and persist its activation/tool state."""
        async with self._lock:
            plugin = self._catalog.plugins.get_by_name(plugin_name)
            if plugin is None:
                raise Exception("插件不存在。")
            await self._extensions.deactivate(plugin, reason="disable")
            await self.terminate_plugin(plugin)
            inactivated_plugins: list = await self._preferences.global_get(
                "inactivated_plugins",
                [],
            )
            if plugin.module_path not in inactivated_plugins:
                inactivated_plugins.append(plugin.module_path)
            inactivated_llm_tools: list = list(
                set(await self._preferences.global_get("inactivated_llm_tools", [])),
            )
            module_prefix = self._catalog.module_prefix(plugin)
            for func_tool in self._catalog.runtime_catalogs.tools.func_list:
                for tool in self._catalog.iter_tool_tree(func_tool):
                    if not self._catalog.tool_is_owned_by_module_prefix(
                        tool,
                        module_prefix,
                    ):
                        continue
                    tool.active = False
                    if tool.name not in inactivated_llm_tools:
                        inactivated_llm_tools.append(tool.name)
            await self._preferences.global_put(
                "inactivated_plugins", inactivated_plugins
            )
            await self._preferences.global_put(
                "inactivated_llm_tools",
                inactivated_llm_tools,
            )
            plugin.activated = False
            await self._refresh_command_surfaces()

    async def turn_on_plugin(self, plugin_name: str) -> None:
        """Enable a disabled plugin and re-create its runtime generation."""
        async with self._lock:
            plugin = self._catalog.plugins.get_by_name(plugin_name)
            if plugin is None:
                raise Exception(f"插件 {plugin_name} 不存在。")
            inactivated_plugins: list = await self._preferences.global_get(
                "inactivated_plugins",
                [],
            )
            inactivated_llm_tools: list = await self._preferences.global_get(
                "inactivated_llm_tools",
                [],
            )
            if plugin.module_path in inactivated_plugins:
                inactivated_plugins.remove(plugin.module_path)
            await self._preferences.global_put(
                "inactivated_plugins", inactivated_plugins
            )
            module_prefix = self._catalog.module_prefix(plugin)
            for func_tool in self._catalog.runtime_catalogs.tools.func_list:
                for tool in self._catalog.iter_tool_tree(func_tool):
                    if not self._catalog.tool_is_owned_by_module_prefix(
                        tool,
                        module_prefix,
                    ):
                        continue
                    if tool.name in inactivated_llm_tools:
                        inactivated_llm_tools.remove(tool.name)
                        tool.active = True
            await self._preferences.global_put(
                "inactivated_llm_tools",
                inactivated_llm_tools,
            )
            success, error = await self._reload_unlocked(plugin_name)
            if not success:
                raise Exception(error or f"插件 {plugin_name} 启用失败。")
            current_plugin = self._catalog.plugins.get_by_name(plugin_name)
            if current_plugin is not None:
                current_plugin.activated = True

    async def terminate_plugin(self, metadata: StarMetadata) -> None:
        """Terminate one plugin instance and invoke unload hooks."""
        logger.info("正在终止插件 %s ...", metadata.name)
        if not metadata.activated:
            logger.debug("插件 %s 未被激活，不需要终止，跳过。", metadata.name)
            return
        if metadata.star_cls is None or metadata.star_cls_type is None:
            return
        if "__del__" in metadata.star_cls_type.__dict__:
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(None, metadata.star_cls.__del__)

            def log_del_exception(fut: asyncio.Future[Any]) -> None:
                if fut.cancelled():
                    return
                if (exc := fut.exception()) is not None:
                    logger.error(
                        "插件 %s 在 __del__ 中抛出了异常：%r", metadata.name, exc
                    )

            future.add_done_callback(log_del_exception)
        elif "terminate" in metadata.star_cls_type.__dict__:
            await metadata.star_cls.terminate()

        for (
            handler
        ) in self._catalog.runtime_catalogs.handlers.get_handlers_by_event_type(
            EventType.OnPluginUnloadedEvent,
        ):
            try:
                source_plugin = self._catalog.plugins.get_by_module(
                    handler.handler_module_path,
                )
                logger.info(
                    "hook(on_plugin_unloaded) -> %s - %s",
                    source_plugin.name if source_plugin else "unknown",
                    handler.handler_name,
                )
                await handler.handler(metadata)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error(traceback.format_exc())

    async def _watch_plugin_changes(self) -> None:
        """Watch plugin packages and reload each activated changed package once."""
        assert awatch is not None and PythonFilter is not None
        try:
            async for changes in awatch(
                self._plugin_store_path,
                self._reserved_plugin_path,
                watch_filter=PythonFilter(),
                recursive=True,
            ):
                await self._handle_file_changes(changes)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("插件热重载监视任务异常")

    async def _handle_file_changes(self, changes: Any) -> None:
        logger.info("检测到文件变化: %s", changes)
        plugin_paths: list[tuple[str, str]] = []
        for plugin in self._catalog.plugins.all():
            if (
                not plugin.activated
                or plugin.root_dir_name is None
                or plugin.name is None
            ):
                continue
            root = (
                self._reserved_plugin_path
                if plugin.reserved
                else self._plugin_store_path
            )
            plugin_paths.append((os.path.join(root, plugin.root_dir_name), plugin.name))
        reloaded: set[str] = set()
        for _change, file_path in changes:
            for plugin_dir_path, plugin_name in plugin_paths:
                if (
                    os.path.commonpath([plugin_dir_path])
                    == os.path.commonpath([plugin_dir_path, file_path])
                    and plugin_name not in reloaded
                ):
                    logger.info("检测到插件 %s 文件变化，正在重载...", plugin_name)
                    await self.reload(plugin_name)
                    reloaded.add(plugin_name)
                    break
