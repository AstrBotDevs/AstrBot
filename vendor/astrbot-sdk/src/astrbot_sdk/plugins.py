from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .errors import CallScopeRetired, HostUnavailable, RemoteError, map_remote_error

if TYPE_CHECKING:
    from .context import PluginContext, PluginInfo

_INSPECT_CAPABILITY = "plugin.inspect"


class PluginRegistryService:
    """Read public metadata of installed plugins and invoke exported services."""

    def __init__(self, ctx: PluginContext[Any]) -> None:
        """Initialize the service.

        Args:
            ctx: Owning plugin context used for Host invocation.
        """
        self._ctx = ctx

    async def get(self, plugin_id: str) -> PluginInfo | None:
        """Return public metadata of one plugin, or None when absent."""
        result = await self._ctx._invoke_capability(
            _INSPECT_CAPABILITY,
            "get",
            {"plugin_id": plugin_id},
        )
        return result.get("plugin")

    async def list(self) -> list[PluginInfo]:
        """Return public metadata of every installed plugin."""
        result = await self._ctx._invoke_capability(
            _INSPECT_CAPABILITY,
            "list",
            {},
        )
        return list(result.get("plugins", []))

    async def call_service(
        self,
        plugin_id: str,
        service: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        """Invoke an exported service on another plugin.

        Requires this plugin to declare a dependency or optional dependency
        on `plugin_id` in its manifest.

        Args:
            plugin_id: Target provider plugin ID or name.
            service: Exported service name on the target plugin.
            payload: JSON-compatible service input object.

        Returns:
            Decoded service result.

        Raises:
            CallScopeRetired: The invocation or instance scope has retired.
            HostUnavailable: No service routing channel is available.
        """
        if self._ctx._retired:
            raise CallScopeRetired("request plugin service scope has retired")
        body = dict(payload or {})
        invoker = self._ctx._host_service_invoker
        if invoker is not None:
            try:
                return await invoker(
                    plugin_id,
                    service,
                    body,
                    self._ctx._ambient_call_id(),
                )
            except RemoteError as exc:
                raise map_remote_error(exc) from exc
        if self._ctx._host_capability_invoker is None:
            raise HostUnavailable("Host plugin service channel is unavailable")
        result = await self._ctx._invoke_capability(
            _INSPECT_CAPABILITY,
            "call_service",
            {"plugin_id": plugin_id, "service": service, "input": body},
        )
        return result.get("result") if isinstance(result, Mapping) else result
