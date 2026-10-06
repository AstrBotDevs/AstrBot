from __future__ import annotations

from typing import Any

from astrbot_sdk.errors import InvalidRequest, NotFound

from astrbot.core import sp


class StorageService:
    """Plugin-scoped KV storage backed by AstrBot shared preferences."""

    capability_id = "storage.kv"

    def __init__(self, plugin_id: str) -> None:
        """Initialize the service.

        Args:
            plugin_id: Storage namespace of the calling plugin.
        """
        self._plugin_id = plugin_id

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve get/set/delete against the plugin KV namespace."""
        key = payload.get("key")
        if not isinstance(key, str) or not key:
            raise InvalidRequest("storage key must be a non-empty string")
        if operation == "get":
            return {
                "value": await sp.get_async(
                    "plugin",
                    self._plugin_id,
                    key,
                    payload.get("default"),
                ),
            }
        if operation == "set":
            await sp.put_async(
                "plugin",
                self._plugin_id,
                key,
                payload.get("value"),
            )
            return {}
        if operation == "delete":
            await sp.remove_async("plugin", self._plugin_id, key)
            return {}
        raise NotFound(f"unknown storage operation: {operation}")
