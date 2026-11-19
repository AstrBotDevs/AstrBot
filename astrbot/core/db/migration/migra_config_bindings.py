"""Migrate legacy routes and overrides into unified configuration bindings."""

from astrbot.core.config_bindings import BINDING_KEY
from astrbot.core.utils.shared_preferences import SharedPreferences


async def migrate_config_bindings(preferences: SharedPreferences) -> None:
    """Move legacy routes and overrides into the common binding record format.

    Args:
        preferences: Initialized preference store. Existing bindings win on retry.
    """
    routes = await preferences.global_get("umop_config_routing")
    for position, (pattern, profile_id) in enumerate((routes or {}).items()):
        existing = await preferences.get_async("umop", pattern, BINDING_KEY)
        if existing is None:
            await preferences.put_async(
                "umop",
                pattern,
                BINDING_KEY,
                {"profile_id": profile_id, "overrides": {}, "order": position},
            )
    if routes is not None:
        await preferences.remove_async("global", "global", "umop_config_routing")

    for record in await preferences.range_get_async("umo", key="config_overrides"):
        binding = await preferences.session_get(record.scope_id, BINDING_KEY, {}) or {}
        overrides = {**record.value["val"], **binding.get("overrides", {})}
        await preferences.session_put(
            record.scope_id,
            BINDING_KEY,
            {"profile_id": binding.get("profile_id"), "overrides": overrides},
        )
        await preferences.session_remove(record.scope_id, "config_overrides")
