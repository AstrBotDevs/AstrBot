from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import NotFound

from ..convert import _json_safe

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class DbService:
    """Serve the db capability for isolated legacy plugins.

    Read-only projections of the core database for the legacy db_helper
    surface. Results exclude message content and strip non-JSON values.
    """

    capability_id = "db.read"

    def __init__(self, context: Context) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context exposing the database.
        """
        self._context = context

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve one db read operation."""
        db = self._context.get_db()
        if operation == "get_umo_aliases":
            umos = payload.get("umos")
            rows = await db.get_umo_aliases(umos if isinstance(umos, list) else None)
            return {
                "aliases": [_json_safe(row.model_dump(mode="json")) for row in rows]
            }
        if operation == "get_conversations":
            rows = await db.get_conversations(
                user_id=payload.get("user_id"),
                platform_id=payload.get("platform_id"),
            )
            conversations = []
            for row in rows:
                data = row.model_dump(mode="json")
                data.pop("content", None)
                conversations.append(_json_safe(data))
            return {"conversations": conversations}
        raise NotFound(f"unknown db operation: {operation}")
