from __future__ import annotations

from typing import Any

from astrbot_sdk.context import PluginInfo, RuntimeMode
from astrbot_sdk.errors import NotFound

from astrbot.core.star.star import star_registry

from ..detect import _BRIDGE_MODULE_PREFIX


def _to_plugin_info(metadata: Any) -> PluginInfo:
    """Convert one StarMetadata entry into the public plugin DTO."""
    module_path = metadata.module_path or ""
    return PluginInfo(
        id=metadata.plugin_id,
        name=metadata.name or "",
        version=metadata.version or "",
        runtime_mode=(
            RuntimeMode.ISOLATED
            if module_path.startswith(f"{_BRIDGE_MODULE_PREFIX}.")
            else RuntimeMode.IN_PROCESS
        ),
        author=metadata.author,
        desc=metadata.desc,
        activated=metadata.activated,
    )


class PluginInspectService:
    """Serve the plugin.inspect capability over the plugin registry."""

    capability_id = "plugin.inspect"

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve get/list operations against installed plugin metadata."""
        if operation == "get":
            plugin_id = str(payload.get("plugin_id", "")).lower()
            for metadata in star_registry:
                if metadata.plugin_id == plugin_id:
                    return {"plugin": _to_plugin_info(metadata)}
            return {"plugin": None}
        if operation == "list":
            return {
                "plugins": [_to_plugin_info(metadata) for metadata in star_registry],
            }
        raise NotFound(f"unknown plugin operation: {operation}")
