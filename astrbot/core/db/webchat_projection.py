"""Maintain display-message links to committed conversation context positions."""

import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select, update

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
                else next(
                    (
                        entry["message"].get("role")
                        for entry in reversed(payload["messages"])
                        if not entry["message"].get("_no_save")
                    ),
                    None,
                )
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
    turn_ids = func.json_each(json.dumps(list(links))).table_valued("value")
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
