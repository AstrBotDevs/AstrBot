from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


@dataclass(slots=True)
class MCPElicitationReply:
    message_text: str
    message_outline: str


@dataclass(slots=True)
class PendingMCPElicitation:
    umo: str
    sender_id: str
    future: asyncio.Future[MCPElicitationReply]


_PENDING_MCP_ELICITATIONS: dict[str, PendingMCPElicitation] = {}


@asynccontextmanager
async def pending_mcp_elicitation(
    umo: str,
    sender_id: str,
) -> AsyncIterator[asyncio.Future[MCPElicitationReply]]:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[MCPElicitationReply] = loop.create_future()

    current = _PENDING_MCP_ELICITATIONS.get(umo)
    if current is not None and not current.future.done():
        raise RuntimeError(
            f"Another MCP elicitation is already pending for session {umo}."
        )

    pending = PendingMCPElicitation(
        umo=umo,
        sender_id=sender_id,
        future=future,
    )
    _PENDING_MCP_ELICITATIONS[umo] = pending

    try:
        yield future
    finally:
        current = _PENDING_MCP_ELICITATIONS.get(umo)
        if current is pending:
            _PENDING_MCP_ELICITATIONS.pop(umo, None)
        if not future.done():
            future.cancel()


def try_capture_pending_mcp_elicitation(event: AstrMessageEvent) -> bool:
    pending = _PENDING_MCP_ELICITATIONS.get(event.unified_msg_origin)
    if pending is None:
        return False

    sender_id = event.get_sender_id()
    if not sender_id or sender_id != pending.sender_id:
        return False

    if pending.future.done():
        _PENDING_MCP_ELICITATIONS.pop(event.unified_msg_origin, None)
        return False

    pending.future.set_result(
        MCPElicitationReply(
            message_text=event.get_message_str() or "",
            message_outline=event.get_message_outline(),
        )
    )
    return True


def submit_pending_mcp_elicitation_reply(
    umo: str,
    sender_id: str,
    reply_text: str,
    *,
    reply_outline: str | None = None,
) -> bool:
    pending = _PENDING_MCP_ELICITATIONS.get(umo)
    if pending is None or pending.sender_id != sender_id:
        return False

    if pending.future.done():
        _PENDING_MCP_ELICITATIONS.pop(umo, None)
        return False

    pending.future.set_result(
        MCPElicitationReply(
            message_text=reply_text,
            message_outline=reply_outline or reply_text,
        )
    )
    return True
