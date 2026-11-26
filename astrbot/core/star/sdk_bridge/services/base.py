from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from astrbot_sdk.errors import NotFound


@runtime_checkable
class HostService(Protocol):
    """Serve one capability namespace for bridged SDK plugins."""

    capability_id: str

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Execute one operation within this service's capability namespace.

        Args:
            operation: Operation name requested by the plugin.
            payload: Decoded operation input.

        Returns:
            Operation result to encode back to the plugin.

        Raises:
            NotFound: The operation is unknown.
            InvalidRequest: The payload is malformed.
        """
        ...


async def dispatch_capability(
    services: dict[str, HostService],
    capability_id: str,
    operation: str,
    payload: dict[str, Any],
    *,
    plugin_id: str,
    logger: logging.Logger,
) -> Any:
    """Route one authorized capability call to its Host service.

    Authorization happens on the client connection before this point; this
    pipeline owns auditing, service lookup, and error propagation.

    Args:
        services: Registry keyed by capability ID.
        capability_id: Granted capability being invoked.
        operation: Operation within the capability namespace.
        payload: Decoded operation input.
        plugin_id: Identity of the calling plugin, used for audit logs.
        logger: Audit logger.

    Returns:
        Service result.

    Raises:
        NotFound: No service serves this capability.
    """
    service = services.get(capability_id)
    if service is None:
        logger.warning(
            "capability call rejected: plugin=%s has no service for %s",
            plugin_id,
            capability_id,
        )
        raise NotFound(f"unknown capability: {capability_id}")
    logger.debug(
        "capability call: plugin=%s %s.%s",
        plugin_id,
        capability_id,
        operation,
    )
    return await service.handle(operation, payload)
