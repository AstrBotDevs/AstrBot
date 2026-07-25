"""Catalog-scoped Dashboard operations for plugin logger overrides."""

from astrbot.core.star.plugin_catalog import PluginCatalog


class PluginLogLevelService:
    """Expose log-level preferences only for plugins live in one runtime."""

    def __init__(self, plugin_catalog: PluginCatalog) -> None:
        self._plugin_catalog = plugin_catalog

    def get_plugin_log_level(self, plugin_name: str) -> str | None:
        """Return a live plugin's override, if it has one."""
        return self._plugin_catalog.get_plugin_log_level(plugin_name)

    def set_plugin_log_level(self, plugin_name: str, level: str | None) -> str | None:
        """Set an override for a live plugin.

        Raises:
            KeyError: If the plugin is not part of the live catalog.
            ValueError: If the level is invalid.
        """
        return self._plugin_catalog.set_plugin_log_level(plugin_name, level)
