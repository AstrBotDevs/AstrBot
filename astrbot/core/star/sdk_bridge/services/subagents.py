"""Host service backing the legacy subagent orchestrator reload path."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest

from ..snapshot import handoff_entries
from .base import HostService

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class SubagentReloadService(HostService):
    """Reload the subagent orchestrator from a config payload.

    Isolated legacy plugins (e.g. subagent managers) call
    ``orchestrator.reload_from_config(cfg)``; the facade forwards the config
    here so the host's runtime handoffs are rebuilt. The reload is
    in-memory only, matching the persona.write semantics: persisting the
    global config stays with the dashboard/config routes.
    """

    capability_id = "subagents.reload"

    def __init__(self, context: Context) -> None:
        """Initialize the service with the core star context."""
        self._context = context

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        if operation != "reload":
            raise InvalidRequest(f"unknown subagents.reload operation: {operation}")
        cfg = payload.get("config")
        if not isinstance(cfg, dict):
            raise InvalidRequest("subagents.reload requires a config dict")
        orchestrator = self._context.subagent_orchestrator
        if orchestrator is None:
            raise InvalidRequest("subagent orchestrator is unavailable")
        await orchestrator.reload_from_config(cfg)
        return {"handoffs": handoff_entries(orchestrator)}
