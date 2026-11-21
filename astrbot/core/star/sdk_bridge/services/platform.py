from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest, NotFound

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class PlatformRawService:
    """Forward raw platform actions from isolated legacy plugins to adapters.

    This is the escape hatch behind the legacy ``event.bot`` surface. It is
    only granted to legacy plugins; new SDK plugins cannot declare it.
    """

    capability_id = "platform.raw"

    def __init__(self, context: Context) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context used for platform manager access.
        """
        self._context = context

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve the call_action operation."""
        if operation != "call_action":
            raise NotFound(f"unknown platform.raw operation: {operation}")
        platform_id = payload.get("platform_id")
        platform = payload.get("platform")
        action = payload.get("action")
        params = payload.get("params")
        if not platform_id or not action or not isinstance(params, dict):
            raise InvalidRequest(
                "platform.raw call_action requires platform_id, action and params",
            )
        adapter = self._find_adapter(platform_id, platform)
        if adapter is None:
            raise NotFound(f"platform not found: {platform_id}")
        bot = getattr(adapter, "bot", None)
        if bot is None:
            raise NotFound(f"platform {platform_id} exposes no bot client")
        client = getattr(bot, "api", bot)
        if hasattr(client, "call_action"):
            result = await client.call_action(action, **params)
        elif hasattr(client, action):
            result = await getattr(client, action)(**params)
        else:
            raise NotFound(
                f"platform {platform_id} does not support raw action: {action}",
            )
        try:
            json.dumps(result)
        except TypeError as e:
            raise InvalidRequest(
                f"raw action {action} returned a non-JSON result: {e}",
            ) from e
        return {"result": result}

    def _find_adapter(self, platform_id: str, platform: str | None) -> Any:
        """Resolve the running adapter by instance id, then by adapter name."""
        insts = self._context.platform_manager.platform_insts
        for inst in insts:
            if inst.meta().id == platform_id:
                return inst
        for inst in insts:
            if inst.meta().name == platform:
                return inst
        return None
