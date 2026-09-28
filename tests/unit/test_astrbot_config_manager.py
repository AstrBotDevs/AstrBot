from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.astrbot_config_mgr import AstrBotConfigManager


def _make_manager():
    """Create a config manager with mocked asynchronous preferences.

    Returns:
        The config manager and its SharedPreferences mock.
    """
    shared_preferences = MagicMock()
    shared_preferences.global_get = AsyncMock()
    shared_preferences.global_put = AsyncMock()
    manager = AstrBotConfigManager(
        default_config=MagicMock(),
        ucr=MagicMock(),
        sp=shared_preferences,
    )
    return manager, shared_preferences


@pytest.mark.asyncio
async def test_initialize_loads_global_profile_mapping():
    manager, shared_preferences = _make_manager()
    shared_preferences.global_get.return_value = None

    with patch.object(manager, "_load_all_configs") as load_all_configs:
        await manager.initialize()

    assert manager.abconf_data == {}
    shared_preferences.global_get.assert_awaited_once_with("abconf_mapping", {})
    load_all_configs.assert_called_once_with()


@pytest.mark.asyncio
async def test_persist_mapping_updates_memory_only_after_storage_succeeds():
    manager, shared_preferences = _make_manager()
    original_mapping = {"existing": {"path": "existing.json", "name": "Existing"}}
    manager.abconf_data = original_mapping
    shared_preferences.global_put.side_effect = RuntimeError("storage failed")

    with pytest.raises(RuntimeError, match="storage failed"):
        await manager._persist_abconf_mapping({"new": {}})

    assert manager.abconf_data is original_mapping


@pytest.mark.asyncio
async def test_create_conf_uses_async_global_preferences(tmp_path):
    manager, shared_preferences = _make_manager()
    manager.abconf_data = {}
    shared_preferences.global_get.return_value = {}
    profile = MagicMock()

    with (
        patch(
            "astrbot.core.astrbot_config_mgr.get_astrbot_config_path",
            return_value=str(tmp_path),
        ),
        patch(
            "astrbot.core.astrbot_config_mgr.AstrBotConfig",
            return_value=profile,
        ),
    ):
        conf_id = await manager.create_conf(config={"timezone": "UTC"}, name="Test")

    profile.save_config.assert_called_once_with()
    assert manager.confs[conf_id] is profile
    shared_preferences.global_get.assert_awaited_once_with("abconf_mapping", {})
    shared_preferences.global_put.assert_awaited_once_with(
        "abconf_mapping",
        {
            conf_id: {
                "path": f"abconf_{conf_id}.json",
                "name": "Test",
            }
        },
    )


@pytest.mark.asyncio
async def test_update_and_delete_conf_use_async_global_preferences(tmp_path):
    manager, shared_preferences = _make_manager()
    conf_id = "profile-id"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{}", encoding="utf-8")
    update_mapping = {
        conf_id: {
            "path": profile_path.name,
            "name": "Before",
        }
    }
    delete_mapping = {
        conf_id: {
            "path": profile_path.name,
            "name": "After",
        }
    }
    manager.abconf_data = update_mapping
    manager.confs[conf_id] = MagicMock()
    shared_preferences.global_get.side_effect = [update_mapping, delete_mapping]

    assert await manager.update_conf_info(conf_id, name="After") is True

    with patch(
        "astrbot.core.astrbot_config_mgr.get_astrbot_config_path",
        return_value=str(tmp_path),
    ):
        assert await manager.delete_conf(conf_id) is True

    assert not profile_path.exists()
    assert conf_id not in manager.confs
    assert manager.abconf_data == {}
    assert shared_preferences.global_get.await_count == 2
    assert shared_preferences.global_put.await_args_list[0].args == (
        "abconf_mapping",
        {
            conf_id: {
                "path": profile_path.name,
                "name": "After",
            }
        },
    )
    assert shared_preferences.global_put.await_args_list[1].args == (
        "abconf_mapping",
        {},
    )
