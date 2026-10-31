"""Tests for provider reload convergence with the configured provider list."""

import logging
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from astrbot.core.provider.manager import ProviderManager


def _decision_provider(
    provider_id: str,
    *,
    enable: bool = True,
    api_base: str = "https://decision.test/v1/systemone",
) -> dict:
    return {
        "id": provider_id,
        "type": "system_one_decision",
        "provider_type": "decision",
        "api_base": api_base,
        "model": "jev-latest",
        "key": "",
        "enable": enable,
    }


@pytest_asyncio.fixture
async def make_manager():
    """Build a ProviderManager backed by an isolated default config."""
    managers: list[ProviderManager] = []

    def _make(providers: list[dict]) -> ProviderManager:
        config = {
            "provider": providers,
            "provider_sources": [],
            "provider_settings": {},
        }
        acm = MagicMock()
        acm.confs = {"default": config}
        acm.default_conf = config
        persona_manager = MagicMock()
        persona_manager.default_persona = ""
        manager = ProviderManager(acm, MagicMock(), persona_manager)
        managers.append(manager)
        return manager

    yield _make

    for manager in managers:
        await manager.terminate()


@pytest.mark.asyncio
async def test_reload_instantiates_provider_added_to_config(make_manager):
    existing = _decision_provider("existing_provider")
    manager = make_manager([existing])
    await manager.load_provider(existing)

    # A config save appends the provider without creating an instance.
    added = _decision_provider("added_provider")
    manager.acm.default_conf["provider"].append(added)

    await manager.reload(existing)

    assert "added_provider" in manager.inst_map
    assert manager.inst_map["added_provider"] in manager.decision_provider_insts


@pytest.mark.asyncio
async def test_reload_skips_disabled_and_agent_runner_providers(make_manager):
    disabled = _decision_provider("disabled_provider", enable=False)
    agent_runner = {
        "id": "agent_runner_provider",
        "type": "agent_runner",
        "provider_type": "agent_runner",
        "enable": True,
    }
    added = _decision_provider("added_provider")
    manager = make_manager([disabled, agent_runner, added])

    loaded_ids: list[str] = []
    original_load_provider = manager.load_provider

    async def record_load_provider(provider_config: dict) -> None:
        loaded_ids.append(provider_config["id"])
        await original_load_provider(provider_config)

    manager.load_provider = record_load_provider

    await manager.reload(disabled)

    assert loaded_ids == ["added_provider"]
    assert "added_provider" in manager.inst_map
    assert "disabled_provider" not in manager.inst_map
    assert "agent_runner_provider" not in manager.inst_map


@pytest.mark.asyncio
async def test_reload_contains_provider_load_failure(make_manager, caplog):
    broken = _decision_provider("broken_provider", api_base="")
    healthy = _decision_provider("healthy_provider")
    existing = _decision_provider("existing_provider")
    manager = make_manager([broken, healthy, existing])
    await manager.load_provider(existing)

    with caplog.at_level(logging.ERROR):
        await manager.reload(existing)

    assert "healthy_provider" in manager.inst_map
    assert "broken_provider" not in manager.inst_map
    assert any("broken_provider" in record.getMessage() for record in caplog.records)
