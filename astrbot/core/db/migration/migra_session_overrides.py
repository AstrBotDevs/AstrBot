"""Migrate legacy session preferences to explicit configuration overrides."""

from astrbot.core import sp
from astrbot.core.session_overrides import (
    PROVIDER_PATHS,
    get_overrides,
    update_overrides,
)
from astrbot.core.umo_alias import normalize_umo_name


async def migrate_session_overrides(acm, db) -> None:
    """Move rules and the current conversation persona without deleting other data.

    Args:
        acm: Profile manager used to determine persona paths and inherited values.
        db: Main database containing conversations and aliases.
    """
    if await sp.global_get("session_overrides_migrated", False):
        return
    keys = [
        "session_service_config",
        "session_plugin_config",
        "kb_config",
        *[f"provider_perf_{kind}" for kind in PROVIDER_PATHS],
        "sel_conv_id",
    ]
    records = {}
    for key in keys:
        for pref in await sp.range_get_async("umo", key=key):
            records.setdefault(pref.scope_id, {})[key] = pref.value["val"]
    for umo, legacy in records.items():
        base = acm.confs.get(acm.get_conf_info(umo)["id"], acm.default_conf)
        persona_path = (
            "agent.config.persona.persona_id"
            if base.get("agent", {}).get("runtime") == "astrbot"
            else "agent.config.persona_id"
        )
        changes = {}
        if cid := legacy.get("sel_conv_id"):
            conv = await db.get_conversation_by_id(cid)
            if conv and conv.persona_id:
                changes[persona_path] = conv.persona_id
        service = legacy.get("session_service_config") or {}
        if service.get("persona_id"):
            changes[persona_path] = service["persona_id"]
        for old, new in (
            ("llm_enabled", "provider_settings.enable"),
            ("tts_enabled", "provider_tts_settings.enable"),
        ):
            if service.get(old) is False:
                changes[new] = False
        if service.get("session_enabled") is False:
            changes["platform_settings.id_blacklist"] = list(
                dict.fromkeys(
                    [
                        *base.get("platform_settings", {}).get("id_blacklist", []),
                        umo,
                    ]
                )
            )
        if name := normalize_umo_name(service.get("custom_name")):
            aliases = await db.get_umo_aliases([umo])
            alias = aliases[0] if aliases else None
            if not alias or not normalize_umo_name(alias.user_alias):
                await db.upsert_umo_alias(
                    umo,
                    alias.creator_sender_id if alias else "",
                    alias.auto_name if alias else None,
                    name,
                )
        plugin = legacy.get("session_plugin_config") or {}
        disabled = plugin.get(umo, plugin).get("disabled_plugins", [])
        if disabled:
            changes["disabled_plugins"] = disabled
        for kind, path in PROVIDER_PATHS.items():
            if value := legacy.get(f"provider_perf_{kind}"):
                changes[path] = value
        kb = legacy.get("kb_config") or {}
        if "kb_ids" in kb:
            # Retrieval accepts IDs, so migration must not depend on loaded KBs.
            changes["kb_names"] = list(kb["kb_ids"])
            changes["kb_final_top_k"] = kb.get("top_k", 5)
        # Existing overrides win on retries after a partially completed migration.
        existing = await get_overrides(umo)
        changes.update(existing)
        await update_overrides(umo, changes)
        for key in keys:
            if key != "sel_conv_id" and key in legacy:
                await sp.session_remove(umo, key)
    await sp.global_put("session_overrides_migrated", True)
