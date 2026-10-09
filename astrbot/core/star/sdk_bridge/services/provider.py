"""Host service backing the legacy provider write path."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest

from .base import HostService

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class ProviderWriteService(HostService):
    """Apply provider selection changes from isolated legacy plugins.

    Mirrors Context.provider_manager.set_provider: with a umo the choice is
    stored as a per-session preference, otherwise as the global default.
    """

    capability_id = "provider.write"

    def __init__(self, context: Context) -> None:
        """Initialize the service with the core star context."""
        self._context = context

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        if operation == "create_provider":
            new_config = payload.get("new_config")
            if not isinstance(new_config, dict):
                raise InvalidRequest("create_provider requires a new_config dict")
            await self._context.provider_manager.create_provider(new_config)
            return {"applied": True}
        if operation == "update_provider":
            origin_id = payload.get("origin_provider_id")
            new_config = payload.get("new_config")
            if not origin_id or not isinstance(new_config, dict):
                raise InvalidRequest(
                    "update_provider requires origin_provider_id and new_config"
                )
            await self._context.provider_manager.update_provider(
                str(origin_id),
                new_config,
            )
            return {"applied": True}
        if operation == "delete_provider":
            provider_id = payload.get("provider_id")
            provider_source_id = payload.get("provider_source_id")
            if not provider_id and not provider_source_id:
                raise InvalidRequest(
                    "delete_provider requires provider_id or provider_source_id"
                )
            await self._context.provider_manager.delete_provider(
                provider_id=str(provider_id) if provider_id else None,
                provider_source_id=(
                    str(provider_source_id) if provider_source_id else None
                ),
            )
            return {"applied": True}
        if operation != "set_provider":
            raise InvalidRequest(f"unknown provider.write operation: {operation}")
        provider_id = payload.get("provider_id")
        provider_type_value = payload.get("provider_type")
        if not provider_id or not provider_type_value:
            raise InvalidRequest(
                "provider.write set_provider requires provider_id and provider_type"
            )
        from astrbot.core.provider.entities import ProviderType

        try:
            provider_type = ProviderType(str(provider_type_value))
        except ValueError:
            raise InvalidRequest(
                f"unknown provider type: {provider_type_value}"
            ) from None
        umo = payload.get("umo")
        await self._context.provider_manager.set_provider(
            str(provider_id),
            provider_type,
            str(umo) if umo else None,
        )
        return {"applied": True}
