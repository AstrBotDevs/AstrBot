"""Maintain display-message links to committed conversation context positions."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import update

from astrbot.core.db.po import ConversationEvent, PlatformMessageHistory


async def project_webchat_event_links(
    session: AsyncSession,
    events: list[ConversationEvent],
    *,
    snapshot: ConversationEvent | None = None,
) -> None:
    """Apply ordered display links inside the event writer's transaction.

    The first user context and latest assistant context are linked to each turn.
    An automatic snapshot then replaces links to its equivalent source position.
    This projection never opens or commits a transaction; failures propagate so
    event insertion, conversation pointers, and display links roll back together.

    Args:
        session: Active transaction owned by ConversationStore.append.
        events: Validated events in append order, including any automatic snapshot.
        snapshot: Optional automatic snapshot whose source links must be moved.
    """
    for event in events:
        kind, payload = event.type, event.payload
        if (
            kind in {"message.appended", "context.rebased"}
            and payload.get("turn_id")
            and (
                kind != "message.appended"
                or (
                    payload.get("include_in_context", True)
                    and not payload["message"].get("_no_save")
                )
            )
        ):
            role = (
                payload["message"].get("role")
                if kind == "message.appended"
                else payload["messages"][-1]["message"].get("role")
                if payload["messages"]
                else None
            )
            if role in {"user", "assistant"}:
                query = update(PlatformMessageHistory).where(
                    PlatformMessageHistory.turn_id == payload["turn_id"],
                    PlatformMessageHistory.content["type"].as_string()
                    == ("user" if role == "user" else "bot"),
                )
                if role == "user":
                    query = query.where(
                        PlatformMessageHistory.context_event_id.is_(None)
                    )
                await session.execute(query.values(context_event_id=event.event_id))

    if snapshot is not None:
        # The new baseline is exactly equivalent to its source tip.
        # Keep already displayed messages forkable after reclamation.
        await session.execute(
            update(PlatformMessageHistory)
            .where(
                PlatformMessageHistory.context_event_id
                == snapshot.payload["source_event_id"]
            )
            .values(context_event_id=snapshot.event_id)
        )
