from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from astrbot_sdk.context import PluginInfo, RuntimeMode
from astrbot_sdk.errors import InvalidRequest, NotFound

from astrbot.core.star.star import star_registry

from ..convert import _json_safe
from ..detect import _BRIDGE_MODULE_PREFIX
from .base import HostService

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


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


class PluginLifecycleService(HostService):
    """Serve the plugin.lifecycle capability (legacy star_manager writes).

    The reload runs as a background task: a full reload terminates the very
    plugin process that issued the call, so the RPC response must be sent
    before the reload starts. Uninstall targets other plugins and is awaited
    so lifecycle errors reach the caller.
    """

    capability_id = "plugin.lifecycle"

    def __init__(self, context: Context) -> None:
        """Initialize the service with the core star context."""
        self._context = context

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        star_manager = self._context._star_manager
        if star_manager is None:
            raise InvalidRequest("plugin lifecycle is not available")
        if operation == "uninstall":
            plugin_name = payload.get("plugin_name")
            if not plugin_name:
                raise InvalidRequest("uninstall requires plugin_name")
            await star_manager.uninstall_plugin(
                str(plugin_name),
                delete_config=bool(payload.get("delete_config", False)),
                delete_data=bool(payload.get("delete_data", False)),
            )
            return {"uninstalled": True}
        if operation == "turn_off":
            await star_manager.turn_off_plugin(str(payload.get("plugin_name", "")))
            return {"done": True}
        if operation == "turn_on":
            await star_manager.turn_on_plugin(str(payload.get("plugin_name", "")))
            return {"done": True}
        if operation == "update":
            await star_manager.update_plugin(
                str(payload.get("plugin_name", "")),
                proxy=str(payload.get("proxy", "")),
                download_url=str(payload.get("download_url", "")),
                repo_url=str(payload.get("repo_url", "")),
            )
            return {"done": True}
        if operation == "install":
            result = await star_manager.install_plugin(
                str(payload.get("repo_url", "")),
                proxy=str(payload.get("proxy", "")),
                ignore_version_check=bool(payload.get("ignore_version_check", False)),
                download_url=str(payload.get("download_url", "")),
            )
            return {"result": _json_safe(result)}
        if operation != "reload":
            raise InvalidRequest(f"unknown plugin.lifecycle operation: {operation}")
        plugin_name = payload.get("plugin_name")
        asyncio.get_running_loop().create_task(
            star_manager.reload(
                specified_plugin_name=str(plugin_name) if plugin_name else None
            )
        )
        return {"reloading": True}
