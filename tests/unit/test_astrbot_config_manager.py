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


@pytest.mark.asyncio
async def test_async_config_resolution_avoids_sync_sqlite_on_cold_cache(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify async config resolution avoids synchronous sqlite3.connect on cold cache."""
    import sqlite3

    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.config.default import DEFAULT_CONFIG
    from astrbot.core.config_bindings import BINDING_KEY
    from astrbot.core.db.sqlite import SQLiteDatabase
    from astrbot.core.platform.message_session import MessageSession
    from astrbot.core.provider.entities import ProviderType
    from astrbot.core.provider.manager import ProviderManager
    from astrbot.core.utils.shared_preferences import SharedPreferences

    db = SQLiteDatabase(str(tmp_path / "data.db"))
    await db.initialize()
    sp_instance = SharedPreferences(
        db_helper=db, json_storage_path=str(tmp_path / "sp.json")
    )
    await sp_instance.initialize()
    try:
        default_conf = AstrBotConfig(
            config_path=str(tmp_path / "cmd_config.json"),
            default_config=DEFAULT_CONFIG,
        )
        profile_conf = AstrBotConfig(
            config_path=str(tmp_path / "abconf_profile_1.json"),
            default_config={**DEFAULT_CONFIG, "wake_prefix": ["!"]},
        )
        profile_conf.save_config()

        umo = "bot1:GroupMessage:group_1"
        await sp_instance.global_put(
            "abconf_mapping",
            {"profile_1": {"path": "abconf_profile_1.json", "name": "Profile 1"}},
        )
        await sp_instance.session_put(
            umo,
            BINDING_KEY,
            {
                "profile_id": "profile_1",
                "overrides": {
                    "agent.config.model.provider_id": "custom_chat",
                    "wake_prefix": ["?"],
                },
            },
        )
        # Clear in-memory overlay to simulate cold cache
        with sp_instance._cache_lock:
            sp_instance._cache.clear()

        ucr = MagicMock()
        ucr.get_conf_id_for_umop.return_value = "route_profile"
        manager = AstrBotConfigManager(default_conf, ucr, sp_instance)
        await manager.initialize()
        manager.confs["profile_1"] = profile_conf

        def fail_sync_connect(*_args, **_kwargs):
            raise AssertionError("synchronous sqlite3.connect should not be called")

        monkeypatch.setattr(sqlite3, "connect", fail_sync_connect)

        info = await manager.get_conf_info_async(umo)
        assert info["id"] == "profile_1"
        assert info["name"] == "Profile 1"

        routed_info = await manager.get_conf_info_async(
            MessageSession.from_str(umo), follow_route=True
        )
        assert routed_info["id"] == "default"

        invalid_info = await manager.get_conf_info_async("not-a-valid-umo")
        assert invalid_info["id"] == "default"

        with sp_instance._cache_lock:
            sp_instance._cache.clear()

        snapshot, override_paths = await manager._create_message_config_async(umo)
        assert snapshot["wake_prefix"] == ["?"]
        assert override_paths == frozenset(
            {"agent.config.model.provider_id", "wake_prefix"}
        )

        conf = await manager.get_conf_async(umo)
        assert conf["wake_prefix"] == ["?"]

        pm = ProviderManager(
            manager,
            db,
            MagicMock(
                default_persona="default",
                persona_v3_config=[],
                personas_v3=[],
                selected_default_persona_v3=None,
            ),
        )
        fake_chat = MagicMock()
        pm.inst_map["custom_chat"] = fake_chat
        resolved = await pm.get_using_provider_async(ProviderType.CHAT_COMPLETION, umo)
        assert resolved is fake_chat
    finally:
        await sp_instance.close()
        await db.engine.dispose()
