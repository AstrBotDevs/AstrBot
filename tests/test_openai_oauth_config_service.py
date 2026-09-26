import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import astrbot.dashboard.services.config_service as config_service_module
from astrbot.core.provider.manager import ProviderManager
from astrbot.dashboard.services.config_service import ProviderConfigService

_SOURCE_READERS = (
    lambda service: service.get_provider_schema()["provider_sources"][0],
    lambda service: service.list_provider_sources()["provider_sources"][0],
    lambda service: service.get_provider_source("openai_oauth")["provider_source"],
)


@pytest.mark.parametrize("read_source", _SOURCE_READERS)
def test_legacy_oauth_source_reads_include_image_model_without_persisting(read_source):
    service, _manager, _reloads = _build_service()
    original = copy.deepcopy(service.config)

    returned = read_source(service)

    assert returned["oauth_image_model"] == ""
    assert returned["oauth_access_token"] == "access-0"
    assert service.config == original
    returned["oauth_access_token"] = "modified-copy"
    returned["oauth_image_model"] = "gpt-image-2"
    assert service.config == original


@pytest.mark.parametrize("read_source", _SOURCE_READERS)
@pytest.mark.parametrize("configured", ["gpt-image-2.5-flare", None])
def test_oauth_source_reads_preserve_existing_image_model(read_source, configured):
    service, _manager, _reloads = _build_service()
    service.config["provider_sources"][0]["oauth_image_model"] = configured

    assert read_source(service)["oauth_image_model"] == configured
    assert service.config["provider_sources"][0]["oauth_image_model"] == configured


@pytest.mark.parametrize("read_source", _SOURCE_READERS)
def test_other_source_type_does_not_gain_image_model(read_source):
    service, _manager, _reloads = _build_service()
    service.config["provider_sources"][0]["type"] = "openai_chat_completion"
    original = copy.deepcopy(service.config)

    assert "oauth_image_model" not in read_source(service)
    assert service.config == original


def _build_service():
    source = {
        "id": "openai_oauth",
        "type": "openai_oauth_chat_completion",
        "provider": "openai",
        "provider_type": "chat_completion",
        "auth_mode": "openai_oauth",
        "oauth_access_token": "access-0",
        "oauth_refresh_token": "refresh-0",
        "oauth_expires_at": "2026-07-22T16:58:10+00:00",
        "oauth_account_id": "account-0",
    }
    config = {
        "provider_sources": [source],
        "provider": [
            {
                "id": "openai_oauth/gpt-5.6-sol",
                "provider_source_id": "openai_oauth",
                "model": "gpt-5.6-sol",
                "enable": True,
            }
        ],
    }
    manager = ProviderManager.__new__(ProviderManager)
    manager.provider_sources_config = config["provider_sources"]
    manager._openai_oauth_shared_states = {}
    reloads = []

    async def reload_provider(provider):
        reloads.append(provider["id"])

    manager.reload = reload_provider
    lifecycle = SimpleNamespace(
        astrbot_config=config,
        provider_manager=manager,
    )
    return ProviderConfigService(lifecycle), manager, reloads


@pytest.mark.asyncio
async def test_source_model_catalog_includes_gpt_6_astra():
    service, _manager, _reloads = _build_service()

    result = await service.list_provider_source_models("openai_oauth")

    assert result["provider_source_id"] == "openai_oauth"
    assert result["models"][0] == "gpt-6-astra"


@pytest.mark.asyncio
async def test_source_upsert_waits_for_shared_refresh_lock():
    service, manager, reloads = _build_service()
    state = manager.get_openai_oauth_shared_state(
        "openai_oauth",
        service.config["provider_sources"][0],
    )
    replacement = {
        "id": "openai_oauth",
        "type": "openai_chat_completion",
        "provider": "openai",
        "provider_type": "chat_completion",
        "auth_mode": "manual",
    }

    with patch.object(
        config_service_module, "save_config", lambda *_args, **_kwargs: None
    ):
        async with state.refresh_lock:
            task = asyncio.create_task(
                service.upsert_provider_source("openai_oauth", replacement)
            )
            await asyncio.sleep(0.01)
            assert service.config["provider_sources"][0]["auth_mode"] == "openai_oauth"
        await task

    assert state.snapshot()["oauth_refresh_token"] == ""
    assert "openai_oauth" not in manager._openai_oauth_shared_states
    assert reloads == ["openai_oauth/gpt-5.6-sol"]


@pytest.mark.asyncio
async def test_source_upsert_preserves_credentials_rotated_after_editor_loaded():
    service, manager, reloads = _build_service()
    stale_editor_copy = service.get_provider_source("openai_oauth")["provider_source"]
    state = manager.get_openai_oauth_shared_state(
        "openai_oauth",
        service.config["provider_sources"][0],
    )
    rotated_credentials = {
        "oauth_access_token": "access-1",
        "oauth_refresh_token": "refresh-1",
        "oauth_expires_at": "2026-07-23T16:58:10+00:00",
    }
    stale_editor_copy["http_proxy"] = "http://127.0.0.1:7890"

    with patch.object(
        config_service_module, "save_config", lambda *_args, **_kwargs: None
    ):
        state.apply(rotated_credentials)
        service.config["provider_sources"][0].update(rotated_credentials)
        await service.upsert_provider_source("openai_oauth", stale_editor_copy)

    persisted = service.get_provider_source("openai_oauth")["provider_source"]
    assert persisted["oauth_access_token"] == "access-1"
    assert persisted["oauth_refresh_token"] == "refresh-1"
    assert persisted["oauth_expires_at"] == "2026-07-23T16:58:10+00:00"
    assert persisted["http_proxy"] == "http://127.0.0.1:7890"
    assert state.snapshot()["oauth_refresh_token"] == "refresh-1"
    assert reloads == ["openai_oauth/gpt-5.6-sol"]


@pytest.mark.asyncio
async def test_oauth_binding_and_disconnect_wait_for_shared_refresh_lock():
    service, manager, _reloads = _build_service()
    state = manager.get_openai_oauth_shared_state(
        "openai_oauth",
        service.config["provider_sources"][0],
    )
    imported = json.dumps(
        {
            "access_token": "imported-access",
            "refresh_token": "imported-refresh",
            "expires_at": "2026-07-23T16:58:10+00:00",
            "account_id": "account-0",
        }
    )

    with patch.object(
        config_service_module, "save_config", lambda *_args, **_kwargs: None
    ):
        async with state.refresh_lock:
            bind_task = asyncio.create_task(
                service.complete_provider_source_openai_oauth(
                    "openai_oauth",
                    imported,
                )
            )
            await asyncio.sleep(0.01)
            assert state.snapshot()["oauth_refresh_token"] == "refresh-0"
        await bind_task

        async with state.refresh_lock:
            disconnect_task = asyncio.create_task(
                service.disconnect_provider_source_openai_oauth("openai_oauth")
            )
            await asyncio.sleep(0.01)
            assert state.snapshot()["oauth_refresh_token"] == "imported-refresh"
        await disconnect_task

    assert state.snapshot()["oauth_refresh_token"] == ""


@pytest.mark.asyncio
async def test_manual_refresh_keeps_rotated_runtime_token_when_save_fails():
    service, manager, _reloads = _build_service()
    state = manager.get_openai_oauth_shared_state(
        "openai_oauth",
        service.config["provider_sources"][0],
    )

    async def fake_refresh(refresh_token, _proxy):
        assert refresh_token == "refresh-0"
        return {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_at": "2026-07-23T16:58:10+00:00",
            "email": "oauth@example.com",
            "account_id": "account-0",
        }

    def fail_save(*_args, **_kwargs):
        raise RuntimeError("save failed")

    with (
        patch.object(config_service_module, "refresh_access_token", fake_refresh),
        patch.object(config_service_module, "save_config", fail_save),
        pytest.raises(RuntimeError, match="save failed"),
    ):
        await service.refresh_provider_source_openai_oauth("openai_oauth")

    snapshot = state.snapshot()
    assert snapshot["oauth_access_token"] == "access-1"
    assert snapshot["oauth_refresh_token"] == "refresh-1"
