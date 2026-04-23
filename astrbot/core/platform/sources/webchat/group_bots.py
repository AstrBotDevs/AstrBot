def serialize_group(group) -> dict | None:
    if not group:
        return None
    return {
        "session_id": group.session_id,
        "creator": group.creator,
        "name": group.name,
        "avatar": group.avatar or "",
        "avatar_attachment_id": group.avatar_attachment_id or "",
        "description": group.description or "",
    }


def serialize_group_bot(bot) -> dict:
    return {
        "bot_id": bot.bot_id,
        "session_id": bot.session_id,
        "name": bot.name,
        "avatar": bot.avatar or "",
        "avatar_attachment_id": bot.avatar_attachment_id or "",
        "conf_id": bot.conf_id,
        "platform_id": bot.platform_id or f"webchat-{bot.bot_id}",
    }


def resolve_mentioned_bots(message_parts: list[dict], bots: list[dict]) -> list[dict]:
    bot_ids = {bot["bot_id"]: bot for bot in bots}
    bot_names = {bot["name"].casefold(): bot for bot in bots}
    resolved: dict[str, dict] = {}

    for part in message_parts:
        if not isinstance(part, dict) or part.get("type") != "at":
            continue
        target = str(part.get("target") or part.get("bot_id") or "").strip()
        name = str(part.get("name") or "").strip().casefold()
        if target in bot_ids:
            resolved[target] = bot_ids[target]
        if name in bot_names:
            bot = bot_names[name]
            resolved[bot["bot_id"]] = bot

    text = "\n".join(
        str(part.get("text") or "")
        for part in message_parts
        if isinstance(part, dict) and part.get("type") == "plain"
    )
    folded_text = text.casefold()
    for bot in bots:
        if f"@{bot['name'].casefold()}" in folded_text:
            resolved[bot["bot_id"]] = bot
    return list(resolved.values())


def resolve_mentioned_bot(message_parts: list[dict], bots: list[dict]) -> dict | None:
    mentioned_bots = resolve_mentioned_bots(message_parts, bots)
    return mentioned_bots[0] if mentioned_bots else None
