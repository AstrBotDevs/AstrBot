from types import SimpleNamespace

import pytest

from astrbot.core.provider.manager import ProviderManager


class SaveCountingConfig(dict[str, object]):
    def __init__(self, initial: dict[str, object]) -> None:
        super().__init__(initial)
        self.save_count = 0

    def save_config(self) -> None:
        self.save_count += 1


class FakeConfigManager:
    def __init__(self, config: SaveCountingConfig) -> None:
        self.confs = {"default": config}

    @property
    def default_conf(self) -> SaveCountingConfig:
        return self.confs["default"]


def make_manager(config: SaveCountingConfig) -> ProviderManager:
    return ProviderManager(
        FakeConfigManager(config),
        db_helper=SimpleNamespace(),
        persona_mgr=SimpleNamespace(default_persona="default"),
    )


@pytest.mark.asyncio
async def test_create_provider_rejects_missing_merged_type_before_saving() -> None:
    config = SaveCountingConfig(
        {
            "provider_sources": [
                {
                    "id": "deepseek_1",
                    "provider_type": "chat_completion",
                    "enable": True,
                }
            ],
            "provider": [],
            "provider_settings": {},
        }
    )
    manager = make_manager(config)

    with pytest.raises(ValueError, match="missing a valid 'type' field"):
        await manager.create_provider(
            {
                "id": "deepseek_1/deepseek-v4-flash",
                "provider_source_id": "deepseek_1",
                "provider_type": "chat_completion",
                "model": "deepseek-v4-flash",
                "enable": True,
            }
        )

    assert config["provider"] == []
    assert config.save_count == 0


@pytest.mark.asyncio
async def test_load_provider_skips_missing_type_without_keyerror() -> None:
    config = SaveCountingConfig(
        {
            "provider_sources": [],
            "provider": [],
            "provider_settings": {},
        }
    )
    manager = make_manager(config)

    await manager.load_provider(
        {
            "id": "missing-type",
            "provider_type": "chat_completion",
            "enable": True,
        }
    )

    assert manager.inst_map == {}
