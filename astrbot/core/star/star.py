from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from astrbot.core.config import AstrBotConfig

if TYPE_CHECKING:
    from . import Star
    from .dashboard_extension import DashboardExtensionManifest


@dataclass
class StarMetadata:
    """插件的元数据。

    当 activated 为 False 时，star_cls 可能为 None，请不要在插件未激活时调用 star_cls 的方法。
    """

    name: str | None = None
    """插件名"""
    author: str | None = None
    """插件作者"""
    desc: str | None = None
    """插件简介"""
    short_desc: str | None = None
    """插件短简介"""
    version: str | None = None
    """插件版本"""
    repo: str | None = None
    """插件仓库地址"""

    star_cls_type: type[Star] | None = None
    """插件的类对象的类型"""
    module_path: str | None = None
    """插件的模块路径"""

    star_cls: Star | None = None
    """插件的类对象"""
    module: ModuleType | None = None
    """插件的模块对象"""
    root_dir_name: str | None = None
    """插件的目录名称"""
    reserved: bool = False
    """是否是 AstrBot 的保留插件"""

    activated: bool = True
    """是否被激活"""

    config: AstrBotConfig | None = None
    """插件配置"""

    star_handler_full_names: list[str] = field(default_factory=list)
    """注册的 Handler 的全名列表"""

    display_name: str | None = None
    """用于展示的插件名称"""

    logo_path: str | None = None
    """插件 Logo 的路径"""

    support_platforms: list[str] = field(default_factory=list)
    """插件声明支持的平台适配器 ID 列表（对应 ADAPTER_NAME_2_TYPE 的 key）"""

    astrbot_version: str | None = None
    """插件要求的 AstrBot 版本范围（PEP 440 specifier，如 >=4.13.0,<4.17.0）"""

    i18n: dict[str, dict] = field(default_factory=dict)
    """插件自带的国际化文案，按 locale 分组。"""

    dashboard: DashboardExtensionManifest | None = None
    """Validated Dashboard Extension Protocol v1 manifest."""

    dashboard_root: Path | None = None
    """Validated real plugin root used by Dashboard resources."""

    authorization_actions: frozenset[str] = field(default_factory=frozenset)
    """Explicit plugin action names declared in metadata.yaml."""

    @property
    def plugin_id(self) -> str:
        p_name = (self.name or "unknown").lower().replace("/", "_")
        p_author = (self.author or "unknown").lower().replace("/", "_")
        return f"{p_author}/{p_name}"

    def __str__(self) -> str:
        return f"Plugin {self.name} ({self.version}) by {self.author}: {self.desc}"

    def __repr__(self) -> str:
        return f"Plugin {self.name} ({self.version}) by {self.author}: {self.desc}"


@dataclass(frozen=True, slots=True)
class StarDeclaration:
    """Static plugin declaration attached to a :class:`Star` subclass.

    Importing a plugin may create declarations, but it must not publish mutable
    state into a process-wide registry.  A runtime catalog materializes this
    declaration only after the plugin module has been validated.
    """

    star_cls_type: type[Star]
    module_path: str


class PluginRegistry:
    """Runtime-owned catalog of published plugins.

    Each application runtime owns one instance.  The catalog deliberately
    exposes query operations instead of a mutable ``dict``/``list`` pair so a
    plugin reload can remove an exact module without affecting another
    runtime.
    """

    def __init__(self) -> None:
        self._by_module: dict[str, StarMetadata] = {}
        self._items: list[StarMetadata] = []

    def publish(self, metadata: StarMetadata) -> None:
        """Publish one fully initialized plugin metadata object.

        Args:
            metadata: Metadata whose ``module_path`` identifies the plugin.

        Raises:
            ValueError: If the metadata has no module path or the module is
                already published by a different object.
        """
        module_path = metadata.module_path
        if not module_path:
            raise ValueError("Plugin metadata must have a module path")
        existing = self._by_module.get(module_path)
        if existing is not None and existing is not metadata:
            raise ValueError(f"Plugin module already published: {module_path}")
        if existing is None:
            if metadata.name:
                same_name = self.get_by_name(metadata.name)
                if same_name is not None and same_name is not metadata:
                    raise ValueError(f"Plugin name already published: {metadata.name}")
            self._by_module[module_path] = metadata
            self._items.append(metadata)

    def replace_module(self, metadata: StarMetadata) -> StarMetadata | None:
        """Atomically replace an exact module after a successful reload.

        The caller prepares and initializes ``metadata`` before invoking this
        method.  A failed preparation therefore leaves the existing catalog
        entry untouched.
        """
        module_path = metadata.module_path
        if not module_path:
            raise ValueError("Plugin metadata must have a module path")
        previous = self._by_module.get(module_path)
        if previous is None:
            self.publish(metadata)
            return None
        if metadata.name:
            same_name = self.get_by_name(metadata.name)
            if same_name is not None and same_name is not previous:
                raise ValueError(f"Plugin name already published: {metadata.name}")
        self._by_module[module_path] = metadata
        self._items[self._items.index(previous)] = metadata
        return previous

    def get_by_module(self, module_path: str | None) -> StarMetadata | None:
        """Return metadata for an exact module path."""
        if not module_path:
            return None
        return self._by_module.get(module_path)

    def get_by_name(self, name: str) -> StarMetadata | None:
        """Return the published plugin with an exact display name."""
        return next((item for item in self._items if item.name == name), None)

    def all(self) -> tuple[StarMetadata, ...]:
        """Return an immutable snapshot in publication order."""
        return tuple(self._items)

    def unregister_module(self, module_path: str) -> StarMetadata | None:
        """Remove and return metadata belonging to one exact module."""
        metadata = self._by_module.pop(module_path, None)
        if metadata is not None:
            self._items.remove(metadata)
        return metadata

    def unregister_prefix(self, module_prefix: str) -> tuple[StarMetadata, ...]:
        """Remove every plugin owned by a module prefix."""
        removed = tuple(
            metadata
            for metadata in self._items
            if metadata.module_path
            and (
                metadata.module_path == module_prefix
                or metadata.module_path.startswith(f"{module_prefix}.")
            )
        )
        for metadata in removed:
            assert metadata.module_path is not None
            self.unregister_module(metadata.module_path)
        return removed

    def clear(self) -> None:
        """Remove all published plugin metadata from this runtime."""
        self._by_module.clear()
        self._items.clear()

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


def collect_star_declaration(module: ModuleType) -> StarDeclaration | None:
    """Find the one Star declaration directly owned by a plugin module.

    Imported classes are intentionally ignored.  A plugin entry module with
    multiple Star declarations is ambiguous and rejected rather than relying
    on import order to select one.
    """
    declarations = [
        candidate.__dict__.get("__astrbot_star_declaration__")
        for candidate in vars(module).values()
        if isinstance(candidate, type) and candidate.__module__ == module.__name__
    ]
    owned = [
        declaration
        for declaration in declarations
        if isinstance(declaration, StarDeclaration)
    ]
    if len(owned) > 1:
        raise ValueError(
            f"Plugin module {module.__name__!r} declares multiple Star classes"
        )
    return owned[0] if owned else None
