from __future__ import annotations

from collections.abc import Callable
from typing import Any

from astrbot_sdk.errors import InvalidRequest, NotFound


class ConfigWriteService:
    """Persist an isolated plugin's own config through the Host.

    The Runner holds a config snapshot; ``config.save_config()`` forwards the
    merged dict here, and the Host writes it through the real AstrBotConfig so
    revision/conflict handling stays identical to in-process plugins. Only
    granted to legacy plugins; new SDK plugins cannot declare it.
    """

    capability_id = "config.write"

    def __init__(
        self,
        config_resolver: Callable[[], Any],
        ucr_resolver: Callable[[], Any] | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            config_resolver: Zero-arg callable returning the plugin's
                AstrBotConfig. Resolved lazily because services are built
                before the legacy config is loaded during start().
            ucr_resolver: Optional zero-arg callable returning the Host's
                UmopConfigRouter for route update/delete operations.
        """
        self._config_resolver = config_resolver
        self._ucr_resolver = ucr_resolver

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve one config.write operation."""
        if operation == "update_route":
            umo = payload.get("umo")
            conf_id = payload.get("conf_id")
            if not isinstance(umo, str) or not isinstance(conf_id, str):
                raise InvalidRequest("update_route requires umo and conf_id strings")
            if self._ucr_resolver is None or self._ucr_resolver() is None:
                raise NotFound("config router unavailable")
            await self._ucr_resolver().update_route(umo, conf_id)
            return {}
        if operation == "delete_route":
            umo = payload.get("umo")
            if not isinstance(umo, str):
                raise InvalidRequest("delete_route requires a umo string")
            if self._ucr_resolver is None or self._ucr_resolver() is None:
                raise NotFound("config router unavailable")
            await self._ucr_resolver().delete_route(umo)
            return {}
        if operation != "save":
            raise NotFound(f"unknown config.write operation: {operation}")
        snapshot = payload.get("config")
        if not isinstance(snapshot, dict):
            raise InvalidRequest("config.write save requires a config object")
        indent = payload.get("indent", 2)
        if not isinstance(indent, int) or indent < 0:
            raise InvalidRequest("config.write save requires a non-negative indent")
        config = self._config_resolver()
        if config is None:
            raise NotFound("plugin has no config to save")
        # The Runner sends its full merged dict, so replace the Host-side
        # content wholesale: keys the plugin deleted must not survive.
        config.clear()
        config.update(snapshot)
        committed = await config.save_config_async(indent=indent)
        return {"committed": committed}
