import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core import astrbot_config_mgr as config_manager_module


@pytest.mark.asyncio
async def test_create_conf_persists_with_async_snapshot_api(monkeypatch, tmp_path):
    created_configs = []

    class FakeConfig:
        def __init__(self, *, config_path: str, default_config: dict) -> None:
            self.config_path = config_path
            self.default_config = default_config
            self.save_config_async = AsyncMock(return_value=True)
            created_configs.append(self)

    monkeypatch.setattr(config_manager_module, "AstrBotConfig", FakeConfig)
    monkeypatch.setattr(
        config_manager_module,
        "get_astrbot_config_path",
        lambda: str(tmp_path),
    )
    preferences = SimpleNamespace(global_put=AsyncMock())
    manager = config_manager_module.AstrBotConfigManager(
        default_config=SimpleNamespace(),
        ucr=SimpleNamespace(),
        sp=preferences,
    )

    config_id = await manager.create_conf(config={"provider": []}, name="profile")

    created = created_configs[0]
    created.save_config_async.assert_awaited_once()
    preferences.global_put.assert_awaited_once_with(
        "abconf_mapping",
        {
            config_id: {
                "path": f"abconf_{config_id}.json",
                "name": "profile",
            },
        },
    )
    assert manager.confs[config_id] is created


@pytest.mark.asyncio
async def test_create_conf_does_not_publish_profile_when_save_is_superseded(
    monkeypatch,
    tmp_path,
):
    created_configs = []

    class FakeConfig:
        def __init__(self, *, config_path: str, default_config: dict) -> None:
            self.config_path = config_path
            self.default_config = default_config
            self.save_config_async = AsyncMock(return_value=False)
            created_configs.append(self)

    monkeypatch.setattr(config_manager_module, "AstrBotConfig", FakeConfig)
    monkeypatch.setattr(
        config_manager_module,
        "get_astrbot_config_path",
        lambda: str(tmp_path),
    )
    preferences = SimpleNamespace(global_put=AsyncMock())
    manager = config_manager_module.AstrBotConfigManager(
        default_config=SimpleNamespace(),
        ucr=SimpleNamespace(),
        sp=preferences,
    )

    with pytest.raises(RuntimeError, match="superseded"):
        await manager.create_conf(config={"provider": []}, name="profile")

    created_configs[0].save_config_async.assert_awaited_once()
    preferences.global_put.assert_not_awaited()
    assert set(manager.confs) == {"default"}


@pytest.mark.asyncio
async def test_create_conf_serializes_concurrent_mapping_updates(monkeypatch, tmp_path):
    class FakeConfig:
        def __init__(self, *, config_path: str, default_config: dict) -> None:
            self.config_path = config_path
            self.default_config = default_config

        async def save_config_async(self) -> bool:
            await asyncio.sleep(0)
            return True

    monkeypatch.setattr(config_manager_module, "AstrBotConfig", FakeConfig)
    monkeypatch.setattr(
        config_manager_module,
        "get_astrbot_config_path",
        lambda: str(tmp_path),
    )
    preferences = SimpleNamespace(global_put=AsyncMock())
    manager = config_manager_module.AstrBotConfigManager(
        default_config=SimpleNamespace(),
        ucr=SimpleNamespace(),
        sp=preferences,
    )

    first, second = await asyncio.gather(
        manager.create_conf(config={}, name="first"),
        manager.create_conf(config={}, name="second"),
    )

    assert {first, second} == set(manager.abconf_data)
    assert {first, second} == set(manager.confs) - {"default"}
    assert preferences.global_put.await_count == 2


@pytest.mark.asyncio
async def test_create_conf_removes_file_when_mapping_persist_fails(
    monkeypatch,
    tmp_path,
):
    class FakeConfig:
        def __init__(self, *, config_path: str, default_config: dict) -> None:
            self.config_path = config_path
            self.default_config = default_config

        async def save_config_async(self) -> bool:
            Path(self.config_path).write_text("{}", encoding="utf-8")
            return True

    monkeypatch.setattr(config_manager_module, "AstrBotConfig", FakeConfig)
    monkeypatch.setattr(
        config_manager_module,
        "get_astrbot_config_path",
        lambda: str(tmp_path),
    )
    preferences = SimpleNamespace(
        global_put=AsyncMock(side_effect=RuntimeError("storage failed")),
    )
    manager = config_manager_module.AstrBotConfigManager(
        default_config=SimpleNamespace(),
        ucr=SimpleNamespace(),
        sp=preferences,
    )

    with pytest.raises(RuntimeError, match="storage failed"):
        await manager.create_conf(config={}, name="failed")

    assert list(tmp_path.iterdir()) == []
    assert set(manager.confs) == {"default"}


@pytest.mark.asyncio
async def test_delete_conf_restores_mapping_when_file_delete_fails(
    monkeypatch,
    tmp_path,
):
    conf_id = "profile-id"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{}", encoding="utf-8")
    mapping = {conf_id: {"path": profile_path.name, "name": "Profile"}}
    preferences = SimpleNamespace(global_put=AsyncMock())
    manager = config_manager_module.AstrBotConfigManager(
        default_config=SimpleNamespace(),
        ucr=SimpleNamespace(),
        sp=preferences,
    )
    manager.abconf_data = mapping
    manager.confs[conf_id] = SimpleNamespace()
    monkeypatch.setattr(
        config_manager_module,
        "get_astrbot_config_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        config_manager_module.os,
        "remove",
        lambda _path: (_ for _ in ()).throw(OSError("permission denied")),
    )

    assert await manager.delete_conf(conf_id) is False

    assert manager.abconf_data == mapping
    assert conf_id in manager.confs
    assert preferences.global_put.await_args_list[0].args[1] == {}
    assert preferences.global_put.await_args_list[1].args[1] == mapping
