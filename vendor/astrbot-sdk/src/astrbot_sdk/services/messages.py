from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..events import UMO
from ..messages import MessageLike, to_message_chain
from .assets import prepare_outbound_chain

if TYPE_CHECKING:
    from ..context import PluginContext

_MESSAGE_SEND_CAPABILITY = "message.send"


@dataclass(frozen=True, slots=True)
class SendReceipt:
    """Acknowledge one proactively sent message."""

    message_id: str


class MessageService:
    """Send messages outside the current event Pipeline."""

    def __init__(self, ctx: PluginContext) -> None:
        """Initialize the message service.

        Args:
            ctx: Owning plugin context used for Host invocation.
        """
        self._ctx = ctx

    async def send(self, umo: UMO, content: MessageLike) -> SendReceipt:
        """Send a message to an arbitrary session.

        Args:
            umo: Target session. The Host validates capability and scope.
            content: Message content converted to a MessageChain.

        Returns:
            Receipt of the sent message.

        Raises:
            CapabilityDenied: ``message.send`` was not granted.
        """
        chain = await prepare_outbound_chain(
            to_message_chain(content),
            self._ctx.assets,
        )
        result = await self._ctx._invoke_capability(
            _MESSAGE_SEND_CAPABILITY,
            "send",
            {"umo": umo, "message": chain},
        )
        message_id = result.get("message_id", "")
        return SendReceipt(message_id=str(message_id))
