from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.star.star_manager import PluginManager

from .compatibility import PriorityCompatibility
from .models import CollectionMetadata, CollectionPlugin, PluginCollection
from .sensitive_filter import SensitiveFilter


@dataclass(slots=True)
class ExportOptions:
    name: str
    description: str = ""
    author: str = ""
    version: str = "1.0.0"
    include_configs: bool = True
    include_priority: bool = True
    exclude_plugins: list[str] | None = None


class CollectionExporter:
    def __init__(self, plugin_manager: PluginManager) -> None:
        self.plugin_manager = plugin_manager

    async def export(self, options: ExportOptions) -> dict[str, Any]:
        exclude = set(options.exclude_plugins or [])

        plugins: list[CollectionPlugin] = []
        plugin_configs: dict[str, Any] | None = {} if options.include_configs else None

        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin.name in exclude:
                continue
            if not plugin.repo:
                continue

            if not plugin.name:
                continue

            plugins.append(
                CollectionPlugin(
                    name=str(plugin.name),
                    repo=plugin.repo,
                    exported_version=plugin.version or "",
                    display_name=plugin.display_name,
                ),
            )

            if options.include_configs and plugin_configs is not None:
                cfg = getattr(plugin, "config", None)
                if cfg is None:
                    continue
                try:
                    cfg_dict = dict(cfg)
                except Exception as e:
                    # Log the exception to help diagnose config conversion issues
                    logger.warning(
                        f"Failed to convert config for plugin {plugin.name}: {e}"
                    )
                    cfg_dict = {}

                # Some plugins may have a missing/None name in edge cases; avoid using None as dict key.
                if not plugin.name:
                    continue
                plugin_configs[str(plugin.name)] = SensitiveFilter.filter_data(cfg_dict)

        created_at = datetime.now(timezone.utc).isoformat()
        metadata = CollectionMetadata(
            name=options.name,
            description=options.description,
            author=options.author,
            version=options.version,
            created_at=created_at,
            astrbot_version=VERSION,
            plugin_count=len(plugins),
        )

        handler_priority_overrides: dict[str, int] | None = None
        if options.include_priority:
            handler_priority_overrides = (
                await PriorityCompatibility.get_priority_overrides()
            )

        collection = PluginCollection(
            schema_version=PluginCollection.SCHEMA_VERSION,
            metadata=metadata,
            plugins=plugins,
            plugin_configs=plugin_configs,
            handler_priority_overrides=handler_priority_overrides,
        )

        payload = collection.to_dict()
        PluginCollection.validate_dict(payload)
        return payload
