"""Maintain display-message links to committed conversation context positions."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select, text, update

from astrbot.core.db import json_value_rows
from astrbot.core.db.po import ConversationEvent, PlatformMessageHistory


async def project_webchat_event_links(
    session: AsyncSession,
    events: list[ConversationEvent],
) -> None:
    """Apply ordered display links inside the event writer's transaction.

    The first user context and latest assistant context are linked to each turn.
    This projection never opens or commits a transaction; failures propagate so
    event insertion, conversation pointers, and display links roll back together.

    Args:
        session: Active transaction owned by ConversationStore.append.
        events: Validated events in append order.
    """
    links: dict[str, dict[str, str]] = {}
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
                turn_links = links.setdefault(payload["turn_id"], {})
                if role == "user":
                    turn_links.setdefault("user", event.event_id)
                else:
                    turn_links["bot"] = event.event_id

    if not links:
        return

    # Look up the roles that have display rows once, using the turn ID index.
    # A single bound parameter also supports batches spanning many turns.
    if session.bind.dialect.name == "postgresql":
        for turn_id in sorted(links):
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:turn_id, 0))"),
                {"turn_id": turn_id},
            )
    turn_ids = json_value_rows(list(links), session.bind.dialect.name)
    display_type = PlatformMessageHistory.content["type"].as_string()
    display_roles = await session.execute(
        select(PlatformMessageHistory.turn_id, display_type)
        .where(col(PlatformMessageHistory.turn_id).in_(select(turn_ids.c.value)))
        .distinct()
    )
    for turn_id, role in display_roles:
        event_id = links[turn_id].get(role)
        if event_id is None:
            continue
        query = update(PlatformMessageHistory).where(
            PlatformMessageHistory.turn_id == turn_id,
            display_type == role,
        )
        if role == "user":
            query = query.where(PlatformMessageHistory.context_event_id.is_(None))
        await session.execute(query.values(context_event_id=event_id))
