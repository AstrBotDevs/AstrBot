"""Host service backing the legacy persona write path."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest

from .base import HostService

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


_V3_KEY_TO_PERSONA_ATTR: dict[str, str] = {
    "prompt": "system_prompt",
    "begin_dialogs": "begin_dialogs",
    "tools": "tools",
    "skills": "skills",
    "custom_error_message": "custom_error_message",
}


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
        """Handle a persona.write host service request.

        Args:
            operation: Operation name (currently only ``"set_field"``).
            payload: Request payload containing ``name``, ``key``, and ``value``.

        Returns:
            Status dictionary confirming the in-memory update was applied.

        Raises:
            InvalidRequest: If the operation, required fields, or persona name are invalid.
        """
        if operation != "set_field":
            raise InvalidRequest(f"unknown persona.write operation: {operation}")
        name = payload.get("name")
        key = payload.get("key")
        if not name or not key:
            raise InvalidRequest("persona.write set_field requires name and key")
        value = payload.get("value")
        persona_mgr = self._context.persona_manager
        if not any(persona.get("name") == name for persona in persona_mgr.personas_v3):
            raise InvalidRequest(f"persona not found: {name}")

        # Keep backing Persona objects in sync before get_v3_persona_data() rebuilds personas_v3.
        attr_name = _V3_KEY_TO_PERSONA_ATTR.get(key)
        if attr_name is not None:
            for persona_obj in getattr(persona_mgr, "personas", None) or ():
                if getattr(persona_obj, "persona_id", None) == name:
                    setattr(persona_obj, attr_name, value)
                    break

        # Refresh the derived v3 config view used by the pipeline.
        persona_mgr.get_v3_persona_data()

        # Also apply directly to personas_v3 for custom keys or mock PersonaManagers.
        for persona in persona_mgr.personas_v3:
            if persona.get("name") == name:
                persona[key] = value
        return {"applied": True}
