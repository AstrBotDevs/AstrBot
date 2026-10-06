"""Host service backing the legacy persona write path."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest

from .base import HostService

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class PersonaWriteService(HostService):
    """Apply in-memory persona field updates from isolated legacy plugins.

    Legacy plugins mutate the shared persona dicts (personas_v3) directly;
    in isolated mode the facade forwards each assignment here so the host's
    in-memory personas stay in sync. Writes are intentionally not persisted
    to disk, matching the in-process shared-state semantics.
    """

    capability_id = "persona.write"

    def __init__(self, context: Context) -> None:
        """Initialize the service with the core star context."""
        self._context = context

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        if operation != "set_field":
            raise InvalidRequest(f"unknown persona.write operation: {operation}")
        name = payload.get("name")
        key = payload.get("key")
        if not name or not key:
            raise InvalidRequest("persona.write set_field requires name and key")
        persona_mgr = self._context.persona_manager
        for persona in persona_mgr.personas_v3:
            if persona.get("name") == name:
                persona[key] = payload.get("value")
                # Refresh the derived v3 config view used by the pipeline.
                persona_mgr.get_v3_persona_data()
                return {"applied": True}
        raise InvalidRequest(f"persona not found: {name}")
