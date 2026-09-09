import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import astrbot.dashboard.services.config_service  # noqa: F401
from astrbot.core.provider.manager import ProviderManager
from astrbot.dashboard.services.config_service import ProviderConfigService


def manager_with_source():
    manager = ProviderManager.__new__(ProviderManager)
    manager.provider_sources_config = [
        {
            "id": "account",
            "provider": "openai",
            "type": "openai_oauth_chat_completion",
            "auth_mode": "openai_oauth",
            "oauth_access_token": "current",
            "oauth_refresh_token": "rotated",
            "proxy": "http://proxy:3128",
        }
    ]
    manager._openai_oauth_shared_states = {}
    return manager


def test_stt_reuses_source_state_without_changing_adapter_type():
    manager = manager_with_source()
    config = {
        "id": "speech",
        "type": "openai_oauth_stt",
        "provider_type": "speech_to_text",
        "oauth_source_id": "account",
        "model": "gpt-4o-transcribe",
        "oauth_refresh_token": "stale",
    }
    merged = manager.get_merged_provider_config(config, runtime=True)
    assert merged["type"] == "openai_oauth_stt"
    assert merged["model"] == "gpt-4o-transcribe"
    assert merged["oauth_shared_state"] is manager.get_openai_oauth_shared_state(
        "account"
    )
    assert "oauth_refresh_token" not in merged
    assert merged["oauth_shared_state"].snapshot()["oauth_refresh_token"] == "rotated"
    assert callable(merged["oauth_persist_callback"])
    assert merged["proxy"] == "http://proxy:3128"
    assert "oauth_shared_state" not in config


@pytest.mark.parametrize("source_id", ["", "missing"])
def test_stt_rejects_missing_oauth_source(source_id):
    with pytest.raises(ValueError, match="OAuth source"):
        manager_with_source().get_merged_provider_config(
            {"type": "openai_oauth_stt", "oauth_source_id": source_id}, runtime=True
        )


def test_stt_rejects_non_oauth_source():
    manager = manager_with_source()
    manager.provider_sources_config[0]["auth_mode"] = "manual"
    with pytest.raises(ValueError, match="OAuth source"):
        manager.get_merged_provider_config(
            {"type": "openai_oauth_stt", "oauth_source_id": "account"}, runtime=True
        )


@pytest.mark.asyncio
async def test_stt_refresh_persists_to_referenced_source():
    manager = manager_with_source()
    calls = []

    async def persist(source_id, patch):
        calls.append((source_id, patch))

    manager._persist_openai_oauth_provider_source_patch = persist
    merged = manager.get_merged_provider_config(
        {"type": "openai_oauth_stt", "oauth_source_id": "account"}, runtime=True
    )
    await merged["oauth_persist_callback"]({"oauth_access_token": "new"})
    assert calls == [("account", {"oauth_access_token": "new"})]


@pytest.mark.asyncio
async def test_source_reload_and_rename_include_stt_dependents():
    service = ProviderConfigService.__new__(ProviderConfigService)
    service.config = {
        "provider": [
            {"id": "speech", "type": "openai_oauth_stt", "oauth_source_id": "account"},
            {"id": "other", "type": "openai_oauth_stt", "oauth_source_id": "other"},
        ]
    }
    service._reload_providers = AsyncMock()
    await service._reload_providers_for_source("account")
    service._reload_providers.assert_awaited_once_with([service.config["provider"][0]])
    affected = service._move_providers_to_source("account", "renamed")
    assert affected == [service.config["provider"][0]]
    assert affected[0]["oauth_source_id"] == "renamed"
    assert service.config["provider"][1]["oauth_source_id"] == "other"


@pytest.mark.asyncio
async def test_source_deletion_terminates_only_its_stt_dependents():
    class Config(dict):
        def save_config(self):
            pass

    manager = manager_with_source()
    config = Config(
        provider=[
            {"id": "speech", "type": "openai_oauth_stt", "oauth_source_id": "account"},
            {"id": "other", "type": "openai_oauth_stt", "oauth_source_id": "other"},
        ]
    )
    manager.resource_lock = asyncio.Lock()
    manager.providers_config = config["provider"]
    manager.acm = SimpleNamespace(default_conf=config)
    manager.terminate_provider = AsyncMock()
    await manager.delete_provider(provider_source_id="account")
    manager.terminate_provider.assert_awaited_once_with("speech")
    assert [p["id"] for p in manager.providers_config] == ["other"]


@pytest.mark.asyncio
async def test_actual_disconnect_stops_stt_and_rebind_reloads_it():
    from tests.test_openai_oauth_config_service import _build_service

    service, manager, reloads = _build_service()
    service.config["provider"].append(
        {
            "id": "speech",
            "type": "openai_oauth_stt",
            "oauth_source_id": "openai_oauth",
            "enable": True,
        }
    )
    manager.terminate_provider = AsyncMock()
    with patch("astrbot.dashboard.services.config_service.save_config"):
        result = await service.disconnect_provider_source_openai_oauth("openai_oauth")
        assert result["source"]["oauth_access_token"] == ""
        manager.terminate_provider.assert_awaited_once_with("speech")
        assert "speech" not in reloads
        await service._persist_provider_source_patch(
            "openai_oauth",
            {
                "auth_mode": "openai_oauth",
                "oauth_access_token": "new",
            },
        )
    assert reloads[-1] == "speech"
    assert service.config["provider"][-1]["enable"] is True
