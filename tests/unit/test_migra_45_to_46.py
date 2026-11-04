from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.db.migration.migra_45_to_46 import migrate_45_to_46
from astrbot.core.umop_config_router import UmopConfigRouter

pytestmark = pytest.mark.unit


def _make_migration(abconf_data: dict):
    preferences = MagicMock()
    preferences.global_put = AsyncMock()
    router = UmopConfigRouter(preferences)
    router.umop_to_conf_id = {"old::route": "existing"}
    manager = AstrBotConfigManager(MagicMock(), router, preferences)
    manager.abconf_data = abconf_data
    return manager, router, preferences


@pytest.mark.asyncio
async def test_migration_validates_then_persists_routing_before_profiles():
    original = {
        "first": {"name": "First", "umop": ["qq:Group:123", "qq:Friend:456"]},
        "second": {"name": "Second", "umop": ["qq:Group:123"]},
        "default": {"name": "Default"},
    }
    expected_profiles = {
        "first": {"name": "First"},
        "second": {"name": "Second"},
        "default": {"name": "Default"},
    }
    expected_routing = {"qq:Group:123": "first", "qq:Friend:456": "first"}
    manager, router, preferences = _make_migration(original)

    await migrate_45_to_46(manager, router)

    assert preferences.global_put.await_args_list[0].args == (
        "umop_config_routing",
        expected_routing,
    )
    assert preferences.global_put.await_args_list[1].args == (
        "abconf_mapping",
        expected_profiles,
    )
    assert router.umop_to_conf_id == expected_routing
    assert manager.abconf_data == expected_profiles
    assert original["first"]["umop"] == ["qq:Group:123", "qq:Friend:456"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "legacy_value",
    ["qq:Group:123", ["malformed"], ["qq:Group:123", 7]],
)
async def test_invalid_legacy_routes_leave_both_stores_untouched(legacy_value):
    original = {"profile": {"name": "Profile", "umop": legacy_value}}
    manager, router, preferences = _make_migration(original)
    original_router_data = router.umop_to_conf_id

    with pytest.raises(ValueError, match="profile"):
        await migrate_45_to_46(manager, router)

    assert manager.abconf_data is original
    assert original["profile"]["umop"] == legacy_value
    assert router.umop_to_conf_id is original_router_data
    preferences.global_put.assert_not_awaited()


@pytest.mark.asyncio
async def test_routing_write_failure_keeps_legacy_profiles_and_router_state():
    original = {"profile": {"name": "Profile", "umop": ["qq:Group:123"]}}
    manager, router, preferences = _make_migration(original)
    original_router_data = router.umop_to_conf_id
    preferences.global_put.side_effect = RuntimeError("routing write failed")

    with pytest.raises(RuntimeError, match="routing write failed"):
        await migrate_45_to_46(manager, router)

    assert manager.abconf_data is original
    assert original["profile"]["umop"] == ["qq:Group:123"]
    assert router.umop_to_conf_id is original_router_data
    preferences.global_put.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_write_failure_can_be_retried_idempotently():
    original = {"profile": {"name": "Profile", "umop": ["qq:Group:123"]}}
    manager, router, preferences = _make_migration(original)

    async def fail_profile_write(key, _value):
        if key == "abconf_mapping":
            raise RuntimeError("profile write failed")

    preferences.global_put.side_effect = fail_profile_write
    with pytest.raises(RuntimeError, match="profile write failed"):
        await migrate_45_to_46(manager, router)

    assert manager.abconf_data is original
    assert original["profile"]["umop"] == ["qq:Group:123"]
    assert router.umop_to_conf_id == {"qq:Group:123": "profile"}

    preferences.global_put.side_effect = None
    preferences.global_put.reset_mock()
    await migrate_45_to_46(manager, router)

    assert manager.abconf_data == {"profile": {"name": "Profile"}}
    assert router.umop_to_conf_id == {"qq:Group:123": "profile"}
    assert [call.args[0] for call in preferences.global_put.await_args_list] == [
        "umop_config_routing",
        "abconf_mapping",
    ]


@pytest.mark.asyncio
async def test_router_keeps_previous_in_memory_data_when_persistence_fails():
    preferences = MagicMock()
    preferences.global_put = AsyncMock(side_effect=RuntimeError("storage failed"))
    router = UmopConfigRouter(preferences)
    original = {"qq:Group:old": "old-profile"}
    router.umop_to_conf_id = original

    with pytest.raises(RuntimeError, match="storage failed"):
        await router.update_routing_data({"qq:Group:new": "new-profile"})

    assert router.umop_to_conf_id is original
