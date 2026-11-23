"""Route profiles through ordered, durable configuration bindings."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.core.config_bindings import BINDING_KEY
from astrbot.core.umop_config_router import UmopConfigRouter


@pytest.fixture
def router(shared_preferences):
    return UmopConfigRouter(shared_preferences)


@pytest.mark.parametrize(
    ("umo", "expected"),
    [
        ("telegram:private:12345", ("telegram", "private", "12345")),
        ("discord:group:channel:123", ("discord", "group", "channel:123")),
        ("telegram::user_456", ("telegram", "", "user_456")),
        ("::", ("", "", "")),
        ("a:b:c:d", ("a", "b", "c:d")),
        ("telegram:private", None),
        ("telegram", None),
        (None, None),
        (123, None),
    ],
)
def test_split_umo_preserves_colons_in_the_session(umo, expected):
    assert UmopConfigRouter._split_umo(umo) == expected


@pytest.mark.parametrize(
    ("pattern", "umo", "expected"),
    [
        ("telegram:private:123", "telegram:private:123", True),
        ("*:group:456", "telegram:group:456", True),
        ("*:group:456", "discord:group:456", True),
        ("telegram:*:123", "telegram:private:123", True),
        ("telegram:*:123", "telegram:group:123", True),
        ("telegram:private:*", "telegram:private:123", True),
        ("telegram:private:*", "telegram:private:abc", True),
        ("*:private:*", "discord:private:456", True),
        ("telegram::123", "telegram::123", True),
        ("telegram::", "telegram:group:room:member", True),
        ("::", "discord:group:room", True),
        ("bot[12]:group:room?", "bot2:group:room7", True),
        ("telegram:private:123", "discord:private:123", False),
        ("telegram:private:123", "telegram:group:123", False),
        ("Bot::", "bot:group:room", False),
        ("invalid", "telegram:private:123", False),
        ("telegram:private:123", "invalid", False),
        ("invalid", "also_invalid", False),
    ],
)
def test_route_pattern_matching_is_component_wise_and_case_sensitive(
    router, pattern, umo, expected
):
    assert router._is_umo_match(pattern, umo) is expected


@pytest.mark.asyncio
async def test_routes_survive_reload_in_priority_order(router, shared_preferences):
    routes = {
        "telegram:private:123": "exact",
        "telegram:private:*": "private",
        "discord:group:*": "groups",
        "::": "fallback",
    }
    await router.update_routing_data(routes)
    restored = UmopConfigRouter(shared_preferences)
    await restored.initialize()

    assert list(restored.umop_to_conf_id.items()) == list(routes.items())
    assert restored.get_conf_id_for_umop("telegram:private:123") == "exact"
    assert restored.get_conf_id_for_umop("telegram:private:456") == "private"
    assert restored.get_conf_id_for_umop("discord:group:room") == "groups"
    assert restored.get_conf_id_for_umop("matrix:group:room") == "fallback"
    assert await shared_preferences.global_get("umop_config_routing") is None
    for position, (pattern, profile_id) in enumerate(routes.items()):
        assert await shared_preferences.get_async("umop", pattern, BINDING_KEY) == {
            "profile_id": profile_id,
            "overrides": {},
            "order": position,
        }


@pytest.mark.asyncio
async def test_unmatched_and_empty_routes_return_none(router):
    assert router.get_conf_id_for_umop("telegram:private:123") is None
    await router.update_route("telegram:private:*", "private")
    assert router.get_conf_id_for_umop("discord:group:123") is None


@pytest.mark.asyncio
async def test_full_replacement_removes_old_routes_without_touching_session_bindings(
    router, shared_preferences
):
    umo = "telegram:private:123"
    exact_binding = {"profile_id": "personal", "overrides": {"plugin_set": ["notes"]}}
    await shared_preferences.session_put(umo, BINDING_KEY, exact_binding)
    await router.update_routing_data({"telegram::": "old", "discord::": "other"})
    await router.update_routing_data({"telegram:private:*": "new"})

    restored = UmopConfigRouter(shared_preferences)
    await restored.initialize()
    assert restored.umop_to_conf_id == {"telegram:private:*": "new"}
    assert await shared_preferences.get_async("umop", "discord::", BINDING_KEY) is None
    assert await shared_preferences.session_get(umo, BINDING_KEY) == exact_binding


@pytest.mark.asyncio
async def test_concurrent_route_updates_do_not_lose_each_other(
    router, shared_preferences
):
    await asyncio.gather(
        router.update_route("telegram:private:*", "private"),
        router.update_route("discord:group:*", "groups"),
    )
    restored = UmopConfigRouter(shared_preferences)
    await restored.initialize()
    assert restored.umop_to_conf_id == {
        "telegram:private:*": "private",
        "discord:group:*": "groups",
    }


@pytest.mark.asyncio
async def test_deleting_a_route_preserves_other_routes_after_reload(
    router, shared_preferences
):
    await router.update_routing_data({"telegram::": "telegram", "discord::": "discord"})
    await router.delete_route("telegram::")
    await router.delete_route("missing::")
    restored = UmopConfigRouter(shared_preferences)
    await restored.initialize()
    assert restored.umop_to_conf_id == {"discord::": "discord"}
    assert await shared_preferences.get_async("umop", "telegram::", BINDING_KEY) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["invalid", "only:two", 42, None])
async def test_invalid_changes_leave_memory_and_storage_unchanged(
    router, shared_preferences, invalid
):
    original = {"telegram::": "keep"}
    await router.update_routing_data(original)
    with pytest.raises(ValueError, match="umop keys must be"):
        await router.update_routing_data({"discord::": "discard", invalid: "bad"})
    with pytest.raises(ValueError, match="umop must be a string"):
        await router.update_route(invalid, "bad")
    with pytest.raises(ValueError, match="umop must be a string"):
        await router.delete_route(invalid)
    restored = UmopConfigRouter(shared_preferences)
    await restored.initialize()
    assert router.umop_to_conf_id == original
    assert restored.umop_to_conf_id == original


@pytest.mark.asyncio
async def test_failed_persistence_does_not_publish_a_new_route(
    router, shared_preferences, monkeypatch
):
    await router.update_route("telegram::", "keep")
    failure = AsyncMock(side_effect=RuntimeError("storage unavailable"))
    monkeypatch.setattr(shared_preferences, "replace_scope_key", failure)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await router.update_route("discord::", "discard")
    assert router.umop_to_conf_id == {"telegram::": "keep"}
    restored = UmopConfigRouter(shared_preferences)
    await restored.initialize()
    assert restored.umop_to_conf_id == {"telegram::": "keep"}


@pytest.mark.asyncio
async def test_initialize_migrates_legacy_routes_once_and_keeps_newer_bindings(
    router, shared_preferences
):
    await shared_preferences.global_put(
        "umop_config_routing", {"telegram::": "legacy", "discord::": "imported"}
    )
    existing = {"profile_id": "newer", "overrides": {}, "order": 0}
    await shared_preferences.put_async("umop", "telegram::", BINDING_KEY, existing)
    umo = "telegram:private:123"
    await shared_preferences.session_put(
        umo, "config_overrides", {"plugin_set": ["legacy"], "disabled_plugins": ["old"]}
    )
    await shared_preferences.session_put(
        umo,
        BINDING_KEY,
        {"profile_id": "personal", "overrides": {"plugin_set": ["new"]}},
    )
    await router.initialize()
    await router.initialize()

    assert router.umop_to_conf_id == {"telegram::": "newer", "discord::": "imported"}
    assert await shared_preferences.global_get("umop_config_routing") is None
    assert await shared_preferences.session_get(umo, "config_overrides") is None
    assert await shared_preferences.session_get(umo, BINDING_KEY) == {
        "profile_id": "personal",
        "overrides": {"plugin_set": ["new"], "disabled_plugins": ["old"]},
    }
