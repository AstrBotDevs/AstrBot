from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest, NotFound

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSesion as MessageSession

from ..convert import to_core_chain, to_core_message_type
from .assets import AssetStore

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class MessageSendService:
    """Proactive message sending through the AstrBot platform manager."""

    capability_id = "message.send"

    def __init__(self, context: Context, store: AssetStore) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context used for platform access.
            store: Asset store used to resolve asset references.
        """
        self._context = context
        self._store = store

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve the send operation."""
        if operation != "send":
            raise NotFound(f"unknown message operation: {operation}")
        umo = payload.get("umo")
        chain = payload.get("message")
        if umo is None or chain is None:
            raise InvalidRequest("message send requires umo and message")
        session = MessageSession(
            platform_name=umo.platform_id,
            message_type=to_core_message_type(umo.message_type),
            session_id=umo.session_id,
        )
        sent = await self._context.send_message(
            session,
            MessageChain(
                chain=to_core_chain(chain, resolve_asset=self._store.resolve),
            ),
        )
        if not sent:
            raise NotFound(f"platform not found: {umo.platform_id}")
        return {"message_id": ""}
