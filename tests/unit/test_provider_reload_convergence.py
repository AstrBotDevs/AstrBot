"""Tests for provider reload convergence with the configured provider list."""

import asyncio
import logging
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from astrbot.core.provider.manager import ProviderManager


class _Config(dict):
    """Default config test double with the save hook the manager calls."""

    def save_config(self) -> None:
        """Do nothing; tests never persist the configuration."""


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

    def _make(
        providers: list[dict], provider_sources: list[dict] | None = None
    ) -> ProviderManager:
        config = _Config(
            {
                "provider": providers,
                "provider_sources": provider_sources or [],
                "provider_settings": {},
            }
        )
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
async def test_reload_loads_provider_that_inherits_enable_from_source(make_manager):
    source = _decision_provider("decision_source")
    # The entry only references the source; enable and provider_type come from it.
    inherited = {"id": "inherited_provider", "provider_source_id": "decision_source"}
    anchor = _decision_provider("anchor_provider")
    manager = make_manager([inherited, anchor], provider_sources=[source])
    await manager.load_provider(anchor)

    await manager.reload(anchor)

    assert "inherited_provider" in manager.inst_map
    assert manager.inst_map["inherited_provider"] in manager.decision_provider_insts


@pytest.mark.asyncio
async def test_reload_of_configured_entry_that_inherits_enable_from_source(make_manager):
    source = _decision_provider("decision_source")
    inherited = {"id": "inherited_provider", "provider_source_id": "decision_source"}
    manager = make_manager([inherited], provider_sources=[source])

    # The provider-source upsert path reloads each entry with its raw config.
    await manager.reload(inherited)

    assert "inherited_provider" in manager.inst_map


@pytest.mark.asyncio
async def test_reload_skips_provider_whose_source_is_disabled(make_manager):
    source = _decision_provider("decision_source", enable=False)
    inherited = {"id": "inherited_provider", "provider_source_id": "decision_source"}
    anchor = _decision_provider("anchor_provider")
    manager = make_manager([inherited, anchor], provider_sources=[source])
    await manager.load_provider(anchor)

    loaded_ids: list[str] = []
    original_load_provider = manager.load_provider

    async def record_load_provider(provider_config: dict) -> None:
        loaded_ids.append(provider_config["id"])
        await original_load_provider(provider_config)

    manager.load_provider = record_load_provider

    await manager.reload(anchor)

    assert loaded_ids == ["anchor_provider"]
    assert "inherited_provider" not in manager.inst_map


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


@pytest.mark.asyncio
async def test_delete_during_reload_does_not_resurrect_provider(make_manager):
    existing = _decision_provider("existing_provider")
    added = _decision_provider("added_provider")
    manager = make_manager([existing, added])
    await manager.load_provider(existing)

    load_started = asyncio.Event()
    release_load = asyncio.Event()
    original_load_provider = manager.load_provider

    async def gated_load_provider(provider_config: dict) -> None:
        if provider_config["id"] == "added_provider":
            # Hold the convergence load open so delete_provider() can interleave.
            load_started.set()
            await release_load.wait()
        await original_load_provider(provider_config)

    manager.load_provider = gated_load_provider

    reload_task = asyncio.create_task(manager.reload(existing))
    await load_started.wait()
    delete_task = asyncio.create_task(
        manager.delete_provider(provider_id="added_provider")
    )
    # Let the delete reach the manager lock before the reload resumes.
    await asyncio.sleep(0)
    release_load.set()
    await asyncio.gather(reload_task, delete_task)

    assert "added_provider" not in manager.inst_map
    assert "added_provider" not in [
        provider.get("id") for provider in manager.providers_config
    ]
    assert "added_provider" not in [
        provider.get("id") for provider in manager.acm.default_conf["provider"]
    ]


@pytest.mark.asyncio
async def test_update_provider_does_not_deadlock_on_the_manager_lock(make_manager):
    existing = _decision_provider("existing_provider")
    manager = make_manager([existing])
    await manager.load_provider(existing)
    original_instance = manager.inst_map["existing_provider"]

    updated = _decision_provider("existing_provider")
    updated["model"] = "new-model"

    # update_provider() holds resource_lock while it reloads; a re-entrant
    # acquisition of the same lock would block here forever.
    await asyncio.wait_for(
        manager.update_provider("existing_provider", updated),
        timeout=5,
    )

    instance = manager.inst_map["existing_provider"]
    assert instance is not original_instance
    assert instance.provider_config["model"] == "new-model"
