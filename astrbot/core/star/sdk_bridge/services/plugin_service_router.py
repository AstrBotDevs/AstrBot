"""Cross-plugin service routing enforcing non-transitive dependency declarations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from astrbot_sdk.errors import (
    CapabilityDenied,
    InvalidRequest,
    ServiceUnavailable,
)


class PluginServiceRouter:
    """Route `plugin.service.invoke` calls between bridged SDK plugins."""

    def __init__(self) -> None:
        self._bridges: list[Any] = []

    def register(self, bridge: Any) -> None:
        """Register an active `SDKPluginBridge` instance."""
        if bridge not in self._bridges:
            self._bridges.append(bridge)

    def unregister(self, bridge: Any) -> None:
        """Remove a stopped `SDKPluginBridge` instance."""
        if bridge in self._bridges:
            self._bridges.remove(bridge)

    def _find_target(self, identifier: str) -> Any | None:
        for bridge in self._bridges:
            if identifier in (
                getattr(bridge, "plugin_id", ""),
                getattr(bridge, "plugin_name", ""),
                getattr(bridge, "root_dir_name", ""),
            ):
                return bridge
        return None

    async def route(
        self,
        caller_bridge: Any,
        target_identifier: str,
        service_name: str,
        payload: Mapping[str, Any],
    ) -> Any:
        """Authorize and invoke `service_name` on `target_identifier` from `caller_bridge`.

        Requires `caller_bridge` to declare a direct `dependencies` or
        `optional_dependencies` entry naming the target plugin (non-transitive).
        """
        if not target_identifier or not service_name:
            raise InvalidRequest("plugin.service.invoke requires target and service")

        caller_meta = getattr(caller_bridge, "manifest_metadata", None)
        if caller_meta is None:
            raise CapabilityDenied(
                "plugin service calls require manifest dependency declarations"
            )

        declared_deps = set(caller_meta.dependencies.keys()) | set(
            caller_meta.optional_dependencies.keys()
        )
        target_bridge = self._find_target(target_identifier)
        target_aliases = {target_identifier}
        if target_bridge is not None:
            for attr in ("plugin_id", "plugin_name", "root_dir_name"):
                val = getattr(target_bridge, attr, "")
                if val:
                    target_aliases.add(val)

        if not (declared_deps & target_aliases):
            raise CapabilityDenied(
                f"plugin {getattr(caller_bridge, 'plugin_id', '')!r} does not declare "
                f"a direct dependency on {target_identifier!r}"
            )

        if target_bridge is None:
            raise ServiceUnavailable(f"target plugin is offline: {target_identifier}")

        return await target_bridge.invoke_service(service_name, payload)
