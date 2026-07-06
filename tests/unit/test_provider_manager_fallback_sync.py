import asyncio
from types import SimpleNamespace

import pytest

import astrbot.core.star.context  # noqa: F401  # 先导入以规避 provider.manager 的循环导入
from astrbot.core.provider.manager import ProviderManager


class FakeConfig(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.save_count = 0

    def save_config(self):
        self.save_count += 1


def _build_manager(config: FakeConfig) -> ProviderManager:
    manager = ProviderManager.__new__(ProviderManager)
    manager.resource_lock = asyncio.Lock()
    manager.acm = SimpleNamespace(default_conf=config)
    manager.providers_config = config["provider"]
    return manager


async def _noop_terminate(provider_id: str) -> None:
    del provider_id


@pytest.mark.asyncio
async def test_delete_provider_removes_fallback_reference():
    config = FakeConfig(
        {
            "provider": [{"id": "p1"}, {"id": "p2"}],
            "provider_settings": {"fallback_chat_models": ["p1", "p2"]},
        }
    )
    manager = _build_manager(config)
    manager.terminate_provider = _noop_terminate

    await manager.delete_provider(provider_id="p1")

    assert config["provider"] == [{"id": "p2"}]
    assert config["provider_settings"]["fallback_chat_models"] == ["p2"]
    assert config.save_count == 1


@pytest.mark.asyncio
async def test_delete_provider_source_removes_all_fallback_references():
    config = FakeConfig(
        {
            "provider": [
                {"id": "p1", "provider_source_id": "src"},
                {"id": "p2", "provider_source_id": "src"},
                {"id": "p3"},
            ],
            "provider_settings": {"fallback_chat_models": ["p1", "p2", "p3"]},
        }
    )
    manager = _build_manager(config)
    manager.terminate_provider = _noop_terminate

    await manager.delete_provider(provider_source_id="src")

    assert config["provider"] == [{"id": "p3"}]
    assert config["provider_settings"]["fallback_chat_models"] == ["p3"]


@pytest.mark.asyncio
async def test_update_provider_renames_fallback_reference():
    config = FakeConfig(
        {
            "provider": [{"id": "p1", "enable": True}],
            "provider_settings": {"fallback_chat_models": ["p1", "p3"]},
        }
    )
    manager = _build_manager(config)
    reloaded = []

    async def _record_reload(new_config: dict) -> None:
        reloaded.append(new_config)

    manager.reload = _record_reload

    await manager.update_provider("p1", {"id": "p1-renamed", "enable": True})

    assert config["provider_settings"]["fallback_chat_models"] == ["p1-renamed", "p3"]
    assert reloaded and reloaded[0]["id"] == "p1-renamed"


@pytest.mark.asyncio
async def test_update_provider_rename_dedupes_stale_target():
    # "p2" 是残留在回退列表里的失效 ID；把 p1 改名为 p2 后不应产生重复项
    config = FakeConfig(
        {
            "provider": [{"id": "p1", "enable": True}],
            "provider_settings": {"fallback_chat_models": ["p1", "p2"]},
        }
    )
    manager = _build_manager(config)

    async def _record_reload(new_config: dict) -> None:
        del new_config

    manager.reload = _record_reload

    await manager.update_provider("p1", {"id": "p2", "enable": True})

    assert config["provider_settings"]["fallback_chat_models"] == ["p2"]


@pytest.mark.asyncio
async def test_update_provider_same_id_keeps_fallback_list():
    config = FakeConfig(
        {
            "provider": [{"id": "p1", "enable": True}],
            "provider_settings": {"fallback_chat_models": ["p1"]},
        }
    )
    manager = _build_manager(config)

    async def _record_reload(new_config: dict) -> None:
        del new_config

    manager.reload = _record_reload

    await manager.update_provider("p1", {"id": "p1", "enable": False})

    assert config["provider_settings"]["fallback_chat_models"] == ["p1"]
