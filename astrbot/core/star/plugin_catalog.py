"""Runtime-owned plugin declarations and command catalog snapshots."""

from __future__ import annotations

import copy
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import FunctionTool, HandoffTool
from astrbot.core.command import CommandCatalogStore, build_command_catalog
from astrbot.core.runtime_catalogs import RuntimeCatalogs

from .register.star_handler import FunctionToolDeclaration, PluginModuleDeclarations
from .star import StarDeclaration, StarMetadata
from .star_handler import EventType, materialize_handler_declarations

if TYPE_CHECKING:
    from astrbot.core.platform.catalog import PlatformAdapterRegistration
    from astrbot.core.provider.catalog import ProviderAdapterRegistration
    from astrbot.core.star.star_handler import StarHandlerMetadata


@dataclass(frozen=True, slots=True)
class PluginPackageSnapshot:
    """The published declarations needed to restore one plugin generation."""

    metadata: StarMetadata
    providers: tuple[ProviderAdapterRegistration, ...]
    platforms: tuple[PlatformAdapterRegistration, ...]
    handlers: tuple[StarHandlerMetadata, ...]
    tools: tuple[FunctionTool, ...]


class PluginCatalog:
    """Publish and remove declarations for exactly one plugin runtime.

    Decorators attach immutable declarations to imported code.  This catalog is
    the sole mutable materialization point for handlers, tools, adapter
    descriptors, and command snapshots.
    """

    __slots__ = (
        "runtime_catalogs",
        "_command_catalogs",
        "_command_catalog_scopes",
        "_live_logging",
    )

    def __init__(
        self,
        runtime_catalogs: RuntimeCatalogs,
        *,
        live_logging: bool = True,
    ) -> None:
        self.runtime_catalogs = runtime_catalogs
        self.runtime_catalogs.tools.bind_plugin_lookup(self.runtime_catalogs.plugins)
        self._command_catalogs: dict[str, CommandCatalogStore] = {}
        self._command_catalog_scopes: dict[str, tuple[str, ...] | None] = {}
        self._live_logging = live_logging

    @property
    def plugins(self):
        """Return the instance-owned plugin registry."""
        return self.runtime_catalogs.plugins

    def publish_plugin(self, metadata: StarMetadata) -> None:
        """Publish metadata and make its logger discoverable in this runtime."""
        self.plugins.publish(metadata)
        self.refresh_plugin_log_modules(metadata)

    def get_plugin_log_level(self, plugin_name: str) -> str | None:
        """Return a live plugin's override, or ``None`` for the core level.

        Stale persisted preferences must not make an unloaded plugin appear in
        the Dashboard, so this lookup is intentionally scoped to the catalog.
        """
        if self.plugins.get_by_name(plugin_name) is None:
            return None
        from astrbot.core.log import LogManager

        return LogManager.get_plugin_log_level(plugin_name)

    def set_plugin_log_level(self, plugin_name: str, level: str | None) -> str | None:
        """Set one live plugin's log-level override.

        Raises:
            KeyError: If the plugin is not published by this runtime.
            ValueError: If ``level`` is not a supported logging level.
        """
        if self.plugins.get_by_name(plugin_name) is None:
            raise KeyError(plugin_name)
        from astrbot.core.log import LogManager

        LogManager.set_plugin_log_level(plugin_name, level)
        return LogManager.get_plugin_log_level(plugin_name)

    def refresh_plugin_log_modules(self, metadata: StarMetadata) -> None:
        """Mark the published package so SDK logging never needs global metadata."""
        plugin_name = metadata.name
        if not isinstance(plugin_name, str) or not plugin_name:
            return
        if metadata.star_cls_type is not None:
            setattr(
                metadata.star_cls_type, "__astrbot_plugin_logger_name__", plugin_name
            )
        if not self._live_logging:
            return
        module_prefix = self.module_prefix(metadata)
        for module_name, module in tuple(sys.modules.items()):
            if isinstance(module, ModuleType) and self.is_plugin_module_path(
                module_name, module_prefix
            ):
                setattr(module, "__astrbot_plugin_logger_name__", plugin_name)

    def _clear_plugin_log_modules(self, metadata: StarMetadata) -> None:
        if not self._live_logging:
            return
        module_prefix = self.module_prefix(metadata)
        plugin_name = metadata.name
        for module_name, module in tuple(sys.modules.items()):
            if (
                isinstance(module, ModuleType)
                and self.is_plugin_module_path(module_name, module_prefix)
                and getattr(module, "__astrbot_plugin_logger_name__", None)
                == plugin_name
            ):
                delattr(module, "__astrbot_plugin_logger_name__")

    @staticmethod
    def module_prefix(metadata: StarMetadata) -> str:
        """Return the package prefix that owns one plugin declaration."""
        if not metadata.module_path:
            raise ValueError(f"Plugin {metadata.name} has no module path")
        if metadata.root_dir_name:
            namespace = "astrbot.builtin_stars" if metadata.reserved else "data.plugins"
            return f"{namespace}.{metadata.root_dir_name}"
        return metadata.module_path.rsplit(".", 1)[0]

    @staticmethod
    def is_plugin_module_path(module_path: str | None, module_prefix: str) -> bool:
        """Return whether a module is the plugin package or one of its children."""
        return bool(
            module_path
            and (
                module_path == module_prefix
                or module_path.startswith(f"{module_prefix}.")
            )
        )

    @classmethod
    def tool_is_owned_by_module_prefix(
        cls,
        tool: FunctionTool,
        module_prefix: str,
    ) -> bool:
        """Return whether a runtime tool belongs to a plugin package."""
        tool_module_path = getattr(tool, "handler_module_path", None)
        if cls.is_plugin_module_path(tool_module_path, module_prefix):
            return True
        return bool(
            isinstance(tool, HandoffTool)
            and tool.agent.tools
            and any(
                isinstance(candidate, FunctionTool)
                and cls.tool_is_owned_by_module_prefix(candidate, module_prefix)
                for candidate in tool.agent.tools
            )
        )

    @staticmethod
    def _resolve_plugin_tool_actions(
        metadata: StarMetadata,
        required_actions: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Validate plugin tool actions against its manifest declaration."""

        resolved: list[str] = []
        prefix = f"plugin:{metadata.plugin_id}:"
        for action in required_actions:
            if not action.startswith("plugin:"):
                resolved.append(action)
                continue
            local_action = action.removeprefix("plugin:")
            resolved_action = (
                f"{prefix}{local_action}" if ":" not in local_action else action
            )
            if (
                not resolved_action.startswith(prefix)
                or resolved_action not in metadata.authorization_actions
            ):
                raise ValueError(
                    f"Plugin tool action is not declared: {resolved_action!r}"
                )
            resolved.append(resolved_action)
        return tuple(resolved)

    @staticmethod
    def iter_tool_tree(tool: FunctionTool):
        """Yield a top-level tool and local tools nested in a handoff."""
        yield tool
        if isinstance(tool, HandoffTool) and tool.agent.tools:
            yield from (
                candidate
                for candidate in tool.agent.tools
                if isinstance(candidate, FunctionTool)
            )

    def materialize_declarations(
        self,
        metadata: StarMetadata,
        declaration: StarDeclaration,
        module_declarations: PluginModuleDeclarations,
    ) -> None:
        """Publish handlers and tools after their declarations are validated."""
        if metadata.module_path != declaration.module_path:
            raise ValueError(
                "Plugin Star declaration module does not match its entry module: "
                f"{declaration.module_path!r} != {metadata.module_path!r}",
            )
        module_path = metadata.module_path
        if not module_path:
            raise ValueError("Plugin metadata must have an entry module path")

        handlers = materialize_handler_declarations(list(module_declarations.handlers))
        for handler in handlers:
            handler.handler_module_path = module_path
            self.runtime_catalogs.handlers.append(handler)

        def create_function_tool(
            tool_declaration: FunctionToolDeclaration,
        ) -> FunctionTool:
            required_actions = self._resolve_plugin_tool_actions(
                metadata,
                tool_declaration.required_actions,
            )
            tool = self.runtime_catalogs.tools.spec_to_func(
                tool_declaration.name,
                list(tool_declaration.parameters),
                tool_declaration.description,
                tool_declaration.handler,
                required_actions=required_actions,
            )
            tool.handler_module_path = module_path
            return tool

        def publish_tool(tool: FunctionTool) -> None:
            existing = next(
                (
                    candidate
                    for candidate in self.runtime_catalogs.tools.func_list
                    if candidate.name == tool.name
                ),
                None,
            )
            if existing is not None:
                raise ValueError(
                    f"Tool name collision for {tool.name!r} while loading "
                    f"plugin {metadata.name}",
                )
            self.runtime_catalogs.tools.func_list.append(tool)

        materialized_tool_names: set[str] = set()
        for tool_declaration in module_declarations.function_tools:
            if tool_declaration.handoff_name is not None:
                continue
            if tool_declaration.name in materialized_tool_names:
                raise ValueError(
                    f"Plugin {metadata.name} declares duplicate tool "
                    f"{tool_declaration.name!r}",
                )
            materialized_tool_names.add(tool_declaration.name)
            publish_tool(create_function_tool(tool_declaration))

        for handoff_declaration in module_declarations.handoffs:
            handoff_tools: list[str | FunctionTool] = [
                tool if isinstance(tool, str) else copy.copy(tool)
                for tool in handoff_declaration.tools
            ]
            handoff_tools.extend(
                create_function_tool(tool_declaration)
                for tool_declaration in handoff_declaration.tool_declarations
            )
            agent = Agent[object](
                name=handoff_declaration.name,
                instructions=handoff_declaration.instruction,
                tools=handoff_tools,
                run_hooks=handoff_declaration.run_hooks,
            )
            handoff_tool = HandoffTool(agent=agent)
            handoff_tool.handler = handoff_declaration.handler
            handoff_tool.handler_module_path = module_path
            publish_tool(handoff_tool)

    def register_adapter_descriptors(self, module_prefix: str) -> None:
        """Discover adapter declarations in an imported plugin package."""
        for module_name, module in tuple(sys.modules.items()):
            if not isinstance(module, ModuleType) or not self.is_plugin_module_path(
                module_name,
                module_prefix,
            ):
                continue
            self.runtime_catalogs.providers.register_module(module)
            self.runtime_catalogs.platforms.register_module(module)

    def unregister_adapter_descriptors(self, module_prefix: str) -> None:
        """Remove provider and platform declarations owned by one plugin."""
        for module_path in self.runtime_catalogs.providers.module_paths(module_prefix):
            self.runtime_catalogs.providers.unregister_module(module_path)
        for module_path in self.runtime_catalogs.platforms.module_paths(module_prefix):
            self.runtime_catalogs.platforms.unregister_module(module_path)

    def remove_module_declarations(self, module_prefix: str) -> None:
        """Remove handlers, tools, and adapter descriptors for one package."""
        for handler in list(self.runtime_catalogs.handlers):
            if self.is_plugin_module_path(handler.handler_module_path, module_prefix):
                self.runtime_catalogs.handlers.remove(handler)

        self.runtime_catalogs.tools.func_list = [
            tool
            for tool in self.runtime_catalogs.tools.func_list
            if not self.tool_is_owned_by_module_prefix(tool, module_prefix)
        ]
        self.unregister_adapter_descriptors(module_prefix)

    def unpublish(self, plugin_module_path: str) -> StarMetadata | None:
        """Unpublish one plugin and every declaration from its package."""
        metadata = self.runtime_catalogs.plugins.get_by_module(plugin_module_path)
        module_prefix = (
            self.module_prefix(metadata)
            if metadata is not None
            else plugin_module_path.rsplit(".", 1)[0]
        )
        if metadata is not None:
            self._clear_plugin_log_modules(metadata)
            self.runtime_catalogs.plugins.unregister_module(plugin_module_path)
        self.remove_module_declarations(module_prefix)
        return metadata

    def validate_staged_package(
        self,
        current: StarMetadata,
        staged: PluginCatalog,
        replacement: StarMetadata,
    ) -> None:
        """Validate a staged plugin generation against this live catalog.

        The staged catalog is intentionally isolated while a new generation is
        imported and initialized.  Checking every collision before touching
        the live generation makes promotion a short, non-failing mutation.

        Args:
            current: The currently published generation being replaced.
            staged: Catalog that owns the fully initialized replacement.
            replacement: Replacement metadata published in ``staged``.

        Raises:
            ValueError: If the staged generation conflicts with an unrelated
                live declaration.
        """
        current_module_path = current.module_path
        replacement_module_path = replacement.module_path
        if not current_module_path or not replacement_module_path:
            raise ValueError("Plugin generations must have module paths")
        if replacement_module_path != current_module_path:
            raise ValueError(
                "A staged plugin generation must retain its entry module path",
            )

        current_prefix = self.module_prefix(current)
        existing_plugin = self.plugins.get_by_name(replacement.name or "")
        if existing_plugin is not None and existing_plugin is not current:
            raise ValueError(f"Plugin name already published: {replacement.name}")

        for registration in staged.runtime_catalogs.providers.registrations():
            existing = self.runtime_catalogs.providers.get(
                registration.descriptor.type,
            )
            if existing is not None and not self.is_plugin_module_path(
                existing.module_path,
                current_prefix,
            ):
                raise ValueError(
                    "Provider adapter type collision while promoting plugin "
                    f"{replacement.name}: {registration.descriptor.type!r}",
                )

        for registration in staged.runtime_catalogs.platforms.registrations():
            existing = self.runtime_catalogs.platforms.get(
                registration.descriptor.name,
            )
            if existing is not None and not self.is_plugin_module_path(
                existing.module_path,
                current_prefix,
            ):
                raise ValueError(
                    "Platform adapter name collision while promoting plugin "
                    f"{replacement.name}: {registration.descriptor.name!r}",
                )

        for handler in staged.runtime_catalogs.handlers:
            existing = self.runtime_catalogs.handlers.get_handler_by_full_name(
                handler.handler_full_name,
            )
            if existing is not None and not self.is_plugin_module_path(
                existing.handler_module_path,
                current_prefix,
            ):
                raise ValueError(
                    "Handler collision while promoting plugin "
                    f"{replacement.name}: {handler.handler_full_name!r}",
                )

        for tool in staged.runtime_catalogs.tools.func_list:
            existing = next(
                (
                    candidate
                    for candidate in self.runtime_catalogs.tools.func_list
                    if candidate.name == tool.name
                ),
                None,
            )
            if existing is not None and not self.tool_is_owned_by_module_prefix(
                existing,
                current_prefix,
            ):
                raise ValueError(
                    "Tool name collision while promoting plugin "
                    f"{replacement.name}: {tool.name!r}",
                )

    def promote_staged_package(
        self,
        current: StarMetadata,
        staged: PluginCatalog,
        replacement: StarMetadata,
    ) -> None:
        """Atomically replace one live plugin package from a staged catalog.

        Call :meth:`validate_staged_package` before starting lifecycle
        teardown.  This method only moves materialized declarations, so it
        cannot execute plugin code or import modules during publication.
        """
        self.validate_staged_package(current, staged, replacement)
        current_module_path = current.module_path
        assert current_module_path is not None

        self.unpublish(current_module_path)

        for registration in staged.runtime_catalogs.providers.registrations():
            self.runtime_catalogs.providers.register(
                registration.descriptor,
                registration.cls_type,
                module_path=registration.module_path,
            )
        for registration in staged.runtime_catalogs.platforms.registrations():
            self.runtime_catalogs.platforms.register(
                registration.descriptor,
                registration.cls_type,
                module_path=registration.module_path,
            )

        self.publish_plugin(replacement)
        for handler in staged.runtime_catalogs.handlers:
            self.runtime_catalogs.handlers.append(handler)
        self.runtime_catalogs.tools.func_list.extend(
            staged.runtime_catalogs.tools.func_list,
        )

    def snapshot_package(self, metadata: StarMetadata) -> PluginPackageSnapshot:
        """Capture one published package before a reload promotion.

        The snapshot intentionally retains declaration object identities. They
        belong to the old, already-live generation and are only used to restore
        that exact generation if a later step in a multi-plugin promotion
        fails.
        """
        module_prefix = self.module_prefix(metadata)
        return PluginPackageSnapshot(
            metadata=metadata,
            providers=tuple(
                registration
                for registration in self.runtime_catalogs.providers.registrations()
                if self.is_plugin_module_path(registration.module_path, module_prefix)
            ),
            platforms=tuple(
                registration
                for registration in self.runtime_catalogs.platforms.registrations()
                if self.is_plugin_module_path(registration.module_path, module_prefix)
            ),
            handlers=tuple(
                handler
                for handler in self.runtime_catalogs.handlers
                if self.is_plugin_module_path(
                    handler.handler_module_path, module_prefix
                )
            ),
            tools=tuple(
                tool
                for tool in self.runtime_catalogs.tools.func_list
                if self.tool_is_owned_by_module_prefix(tool, module_prefix)
            ),
        )

    def restore_package(self, snapshot: PluginPackageSnapshot) -> None:
        """Restore a package captured by :meth:`snapshot_package`.

        This is the inverse of a successful staged promotion for catalog-owned
        declarations. It does not execute plugin code, so callers can use it
        while unwinding a failed batch transaction.
        """
        metadata = snapshot.metadata
        module_path = metadata.module_path
        if not module_path:
            raise ValueError("Plugin package snapshot has no module path")

        current = self.plugins.get_by_module(module_path)
        if current is not None:
            self.remove_module_declarations(self.module_prefix(current))
            self._clear_plugin_log_modules(current)
            self.plugins.replace_module(metadata)
        else:
            # A promotion can theoretically fail after unpublishing the old
            # metadata but before publishing the replacement. Remove any
            # partially copied declarations for the canonical package first.
            self.remove_module_declarations(self.module_prefix(metadata))
            self.publish_plugin(metadata)
        self.refresh_plugin_log_modules(metadata)

        for registration in snapshot.providers:
            self.runtime_catalogs.providers.register(
                registration.descriptor,
                registration.cls_type,
                module_path=registration.module_path,
            )
        for registration in snapshot.platforms:
            self.runtime_catalogs.platforms.register(
                registration.descriptor,
                registration.cls_type,
                module_path=registration.module_path,
            )
        for handler in snapshot.handlers:
            self.runtime_catalogs.handlers.append(handler)
        self.runtime_catalogs.tools.func_list.extend(snapshot.tools)

    def cleanup_failed_package(
        self, dir_name: str, *, reserved: bool
    ) -> list[StarMetadata]:
        """Remove catalog state published by a partially loaded package."""
        namespace = "astrbot.builtin_stars" if reserved else "data.plugins"
        module_prefix = f"{namespace}.{dir_name}"
        removed: list[StarMetadata] = []
        for metadata in self.runtime_catalogs.plugins.all():
            if self.is_plugin_module_path(metadata.module_path, module_prefix) or (
                metadata.root_dir_name == dir_name and metadata.reserved == reserved
            ):
                if metadata.module_path:
                    self._clear_plugin_log_modules(metadata)
                    self.runtime_catalogs.plugins.unregister_module(
                        metadata.module_path
                    )
                removed.append(metadata)
        self.remove_module_declarations(module_prefix)
        return removed

    def get_command_catalog(
        self,
        config_id: str,
        plugin_names: list[str] | None,
    ) -> CommandCatalogStore:
        """Return the snapshot catalog used by a pipeline configuration."""
        scope = tuple(sorted(plugin_names)) if plugin_names is not None else None
        store = self._command_catalogs.setdefault(config_id, CommandCatalogStore())
        if (
            config_id not in self._command_catalog_scopes
            or self._command_catalog_scopes[config_id] != scope
        ):
            self._command_catalog_scopes[config_id] = scope
            self._replace_command_catalog(store, scope)
        return store

    def refresh_command_catalogs(self) -> None:
        """Atomically rebuild all registered pipeline command snapshots."""
        for config_id, store in self._command_catalogs.items():
            self._replace_command_catalog(
                store,
                self._command_catalog_scopes.get(config_id),
            )

    def _replace_command_catalog(
        self,
        store: CommandCatalogStore,
        plugin_names: tuple[str, ...] | None,
    ) -> None:
        handlers = self.runtime_catalogs.handlers.get_handlers_by_event_type(
            EventType.AdapterMessageEvent,
            plugins_name=list(plugin_names) if plugin_names is not None else None,
        )
        store.replace(build_command_catalog(handlers))
