import asyncio
import copy
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.catalog import PlatformAdapterDescriptor, PlatformCatalog
from astrbot.core.platform.sources.napcat.napcat_platform_adapter import (
    NAPCAT_CONFIG_METADATA,
)
from astrbot.core.provider.catalog import ProviderCatalog
from astrbot.core.utils.llm_metadata import LLMMetadataCatalog
from astrbot.core.utils.totp import TotpRuntimeState
from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.services import config_service


def _runtime(
    *,
    config: dict,
    provider_manager: object | None = None,
    platform_catalog: PlatformCatalog | None = None,
    provider_catalog: ProviderCatalog | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        astrbot_config=config,
        provider_manager=provider_manager
        or SimpleNamespace(dynamic_import_provider=lambda _provider_type: None),
        catalogs=SimpleNamespace(
            platforms=platform_catalog or PlatformCatalog(),
            providers=provider_catalog or ProviderCatalog(),
            plugins=SimpleNamespace(all=lambda: ()),
        ),
    )


def test_ensure_dashboard_platform_metadata_loaded_imports_napcat_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported: list[str] = []
    catalog = PlatformCatalog()

    monkeypatch.setattr(
        config_service,
        "discover_platform_adapter",
        lambda adapter_type, _catalog: imported.append(adapter_type),
    )

    config_service._ensure_dashboard_platform_metadata_loaded(catalog)

    assert imported == ["napcat"]


def test_ensure_dashboard_platform_metadata_loaded_skips_import_when_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = PlatformCatalog()
    adapter = type("NapCatAdapter", (), {})
    catalog.register(
        PlatformAdapterDescriptor.create(
            name="napcat",
            description="NapCat",
            default_config_tmpl=None,
            adapter_display_name=None,
            logo_path=None,
            support_streaming_message=True,
            i18n_resources=None,
            config_metadata=None,
        ),
        adapter,
    )

    def _unexpected_discovery(_: str, __: PlatformCatalog) -> None:
        raise AssertionError("discovery should not be called")

    monkeypatch.setattr(
        config_service,
        "discover_platform_adapter",
        _unexpected_discovery,
    )

    config_service._ensure_dashboard_platform_metadata_loaded(catalog)


def test_sensitive_config_changed_ignores_redacted_placeholders() -> None:
    current = {
        "provider": [{"id": "demo", "api_key": "secret"}],
        "plain": "before",
    }
    posted = {
        "provider": [
            {"id": "demo", "api_key": config_service.REDACTED_SECRET_PLACEHOLDER}
        ],
        "plain": "after",
    }

    assert not config_service.sensitive_config_changed(
        current, posted, missing_is_change=False
    )
    posted["provider"][0]["api_key"] = "new-secret"
    assert config_service.sensitive_config_changed(
        current, posted, missing_is_change=False
    )

    list_current = {"key": ["secret-1", "secret-2"]}
    list_redacted = {
        "key": [
            config_service.REDACTED_SECRET_PLACEHOLDER,
            config_service.REDACTED_SECRET_PLACEHOLDER,
        ]
    }
    assert not config_service.sensitive_config_changed(
        list_current, list_redacted, missing_is_change=False
    )
    list_redacted["key"][1] = "new-secret"
    assert config_service.sensitive_config_changed(
        list_current, list_redacted, missing_is_change=False
    )


def test_profile_and_system_config_responses_redact_secrets() -> None:
    current = {
        "dashboard": {"jwt_secret": "jwt-secret"},
        "provider": [{"id": "demo", "api_key": "provider-secret"}],
        "provider_sources": [],
        "platform": [],
    }
    service = config_service.ConfigProfileService(
        SimpleNamespace(confs={"default": current}),
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
    )

    assert (
        service.get_profile("default")["config"]["provider"][0]["api_key"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )
    assert (
        service.get_system_config()["config"]["dashboard"]["jwt_secret"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )


def test_provider_source_response_strips_removed_responses_web_search_fields():
    runtime = _runtime(config={})
    service = config_service.ProviderConfigService(
        runtime.astrbot_config,
        runtime.provider_manager,
        runtime.catalogs.providers,
        LLMMetadataCatalog(),
    )

    normalized = service._ensure_provider_type(
        {
            "type": "openai_responses",
            "web_search": {
                "enable": True,
                "allowed_domains": ["example.com"],
                "blocked_domains": ["removed.example"],
                "external_web_access": True,
                "return_token_budget": "unlimited",
            },
        }
    )

    assert normalized["web_search"] == {
        "enable": True,
        "allowed_domains": ["example.com"],
    }


@pytest.mark.asyncio
async def test_get_astrbot_config_loads_dashboard_platform_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[bool] = []

    monkeypatch.setattr(
        config_service,
        "_ensure_dashboard_platform_metadata_loaded",
        lambda _catalog: called.append(True),
    )
    runtime = _runtime(config={})
    service = config_service.ConfigDisplayService(
        runtime.astrbot_config,
        runtime.catalogs.platforms,
        runtime.catalogs.providers,
        runtime.catalogs.plugins,
        SimpleNamespace(register_file=AsyncMock()),
    )

    result = await service.get_astrbot_config()

    assert called == [True]
    assert "metadata" in result
    assert "config" in result


@pytest.mark.asyncio
async def test_get_astrbot_config_redacts_sensitive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_service,
        "_ensure_dashboard_platform_metadata_loaded",
        lambda _catalog: None,
    )
    runtime = _runtime(
        config={
            "dashboard": {
                "jwt_secret": "jwt-secret",
                "pbkdf2_password": "pbkdf2-hash",
                "totp": {
                    "enable": True,
                    "secret": "totp-secret",
                    "recovery_code_hash": "recovery-hash",
                },
            },
            "provider": [
                {"id": "demo", "key": ["sk-live-1", "sk-live-2"]},
                {"id": "embed", "embedding_api_key": "embed-secret"},
            ],
            "provider_settings": {"default_provider_id": "demo"},
        },
    )
    service = config_service.ConfigDisplayService(
        runtime.astrbot_config,
        runtime.catalogs.platforms,
        runtime.catalogs.providers,
        runtime.catalogs.plugins,
        SimpleNamespace(register_file=AsyncMock()),
    )

    result = await service.get_astrbot_config()
    redacted = result["config"]

    assert (
        redacted["dashboard"]["jwt_secret"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )
    assert (
        redacted["dashboard"]["pbkdf2_password"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )
    assert (
        redacted["dashboard"]["totp"]["secret"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )
    assert (
        redacted["dashboard"]["totp"]["recovery_code_hash"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )
    assert redacted["provider"][0]["key"] == [
        config_service.REDACTED_SECRET_PLACEHOLDER,
        config_service.REDACTED_SECRET_PLACEHOLDER,
    ]
    assert (
        redacted["provider"][1]["embedding_api_key"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )
    assert redacted["provider_settings"]["default_provider_id"] == "demo"


def test_inject_platform_metadata_with_i18n_rewrites_field_labels() -> None:
    metadata = {
        "platform_group": {
            "metadata": {
                "platform": {
                    "items": {},
                }
            }
        }
    }
    translations: dict = {}
    platform = SimpleNamespace(
        name="napcat",
        config_metadata={
            "ws_url": {
                "description": "NapCat WebSocket URL",
                "hint": "NapCat OneBot v11 forward WebSocket URL.",
            },
            "max_frame_size_mb": {
                "description": "Max Frame Size MB",
                "hint": "Maximum inbound WebSocket frame size in megabytes.",
                "collapsed": True,
            },
        },
        i18n_resources={
            "zh-CN": {
                "ws_url": {
                    "description": "NapCat WebSocket 地址",
                    "hint": "NapCat OneBot v11 正向 WebSocket 地址。",
                },
                "max_frame_size_mb": {
                    "description": "最大帧大小(MB)",
                    "hint": "允许接收的单个 WebSocket 帧的最大大小，单位 MB。",
                },
            },
            "ru-RU": {
                "ws_url": {
                    "description": "Russian URL",
                    "hint": "Russian hint",
                }
            },
        },
    )

    config_service.ConfigDisplayService.inject_platform_metadata_with_i18n(
        platform,
        metadata,
        translations,
    )

    assert metadata["platform_group"]["metadata"]["platform"]["items"]["ws_url"] == {
        "description": "platform_group.platform.napcat.ws_url.description",
        "hint": "platform_group.platform.napcat.ws_url.hint",
    }
    assert metadata["platform_group"]["metadata"]["platform"]["items"][
        "max_frame_size_mb"
    ] == {
        "description": "platform_group.platform.napcat.max_frame_size_mb.description",
        "hint": "platform_group.platform.napcat.max_frame_size_mb.hint",
        "collapsed": True,
    }
    assert translations["zh-CN"]["platform_group"]["platform"]["napcat"] == {
        "ws_url": {
            "description": "NapCat WebSocket 地址",
            "hint": "NapCat OneBot v11 正向 WebSocket 地址。",
        },
        "max_frame_size_mb": {
            "description": "最大帧大小(MB)",
            "hint": "允许接收的单个 WebSocket 帧的最大大小，单位 MB。",
        },
    }
    assert "ru-RU" not in translations


def test_list_bot_types_includes_supported_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakePlatformClass:
        @classmethod
        def declared_supported_actions(cls) -> list[str]:
            return ["send_poke", "send_like"]

    catalog = PlatformCatalog()
    catalog.register(
        PlatformAdapterDescriptor.create(
            name="napcat",
            description="NapCat platform adapter",
            default_config_tmpl={"type": "napcat"},
            adapter_display_name="NapCat",
            logo_path=None,
            support_streaming_message=False,
            i18n_resources=None,
            config_metadata={"ws_url": {"type": "string"}},
        ),
        _FakePlatformClass,
    )
    monkeypatch.setattr(
        config_service,
        "_ensure_dashboard_platform_metadata_loaded",
        lambda _catalog: None,
    )

    runtime = _runtime(config={}, platform_catalog=catalog)
    service = config_service.BotConfigService(
        runtime.astrbot_config,
        runtime.catalogs.platforms,
        SimpleNamespace(),
    )

    result = service.list_bot_types()

    assert result["bot_types"][0]["supported_actions"] == ["send_poke", "send_like"]


def test_napcat_config_metadata_uses_supported_numeric_types() -> None:
    assert NAPCAT_CONFIG_METADATA["timeout_seconds"]["type"] == "float"
    assert NAPCAT_CONFIG_METADATA["reconnect_interval_seconds"]["type"] == "float"
    assert NAPCAT_CONFIG_METADATA["max_frame_size_mb"]["type"] == "int"


def test_napcat_config_metadata_hides_advanced_ws_fields_by_default() -> None:
    assert NAPCAT_CONFIG_METADATA["token"]["collapsed"] is True
    assert NAPCAT_CONFIG_METADATA["verify_ssl"]["collapsed"] is True
    assert NAPCAT_CONFIG_METADATA["timeout_seconds"]["collapsed"] is True
    assert NAPCAT_CONFIG_METADATA["reconnect_interval_seconds"]["collapsed"] is True
    assert NAPCAT_CONFIG_METADATA["max_frame_size_mb"]["collapsed"] is True


@pytest.mark.asyncio
async def test_save_config_async_propagates_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_service,
        "validate_config",
        lambda *args, **kwargs: (_ for _ in ()).throw(asyncio.CancelledError()),
    )

    with pytest.raises(asyncio.CancelledError):
        await config_service.save_config_async(
            {},
            SimpleNamespace(save_config_async=AsyncMock()),
        )


@pytest.mark.asyncio
async def test_save_config_async_restores_redacted_sensitive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_service,
        "validate_config",
        lambda post_config, _schema, _is_core: ([], post_config),
    )

    class FakeConfig(dict):
        def __init__(self, initial: dict) -> None:
            super().__init__(copy.deepcopy(initial))
            self.saved = None

        async def save_config_async(
            self,
            post_config=None,
            *,
            indent: int = 2,
        ) -> None:  # noqa: ARG002
            self.saved = copy.deepcopy(post_config)
            self.clear()
            self.update(post_config)

    current = FakeConfig(
        {
            "dashboard": {
                "jwt_secret": "jwt-secret",
                "pbkdf2_password": "pbkdf2-hash",
                "totp": {
                    "enable": True,
                    "secret": "totp-secret",
                    "recovery_code_hash": "recovery-hash",
                },
            },
            "provider": [
                {"id": "demo", "key": ["sk-live-1", "sk-live-2"]},
                {"id": "embed", "embedding_api_key": "embed-secret"},
            ],
            "provider_settings": {"default_provider_id": "demo"},
        }
    )
    posted = {
        "dashboard": {
            "jwt_secret": config_service.REDACTED_SECRET_PLACEHOLDER,
            "pbkdf2_password": config_service.REDACTED_SECRET_PLACEHOLDER,
            "totp": {
                "enable": True,
                "secret": config_service.REDACTED_SECRET_PLACEHOLDER,
                "recovery_code_hash": config_service.REDACTED_SECRET_PLACEHOLDER,
            },
        },
        "provider": [
            {
                "id": "demo",
                "key": [
                    config_service.REDACTED_SECRET_PLACEHOLDER,
                    config_service.REDACTED_SECRET_PLACEHOLDER,
                ],
            },
            {
                "id": "embed",
                "embedding_api_key": config_service.REDACTED_SECRET_PLACEHOLDER,
            },
        ],
        "provider_settings": {"default_provider_id": "embed"},
    }

    await config_service.save_config_async(posted, current, is_core=True)

    assert current.saved["dashboard"]["jwt_secret"] == "jwt-secret"
    assert current.saved["dashboard"]["pbkdf2_password"] == "pbkdf2-hash"
    assert current.saved["dashboard"]["totp"]["secret"] == "totp-secret"
    assert current.saved["dashboard"]["totp"]["recovery_code_hash"] == "recovery-hash"
    assert current.saved["provider"][0]["key"] == ["sk-live-1", "sk-live-2"]
    assert current.saved["provider"][1]["embedding_api_key"] == "embed-secret"
    assert current.saved["provider_settings"]["default_provider_id"] == "embed"


@pytest.mark.asyncio
async def test_save_config_async_uses_plain_dict_snapshot_for_live_config(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_service,
        "validate_config",
        lambda post_config, _schema, _is_core: ([], post_config),
    )

    config_path = tmp_path / "cmd_config.json"
    config_path.write_text('{"config_version": 2}', encoding="utf-8")

    config = AstrBotConfig(config_path=str(config_path), default_config={})
    object.__setattr__(config, "_runtime_lock", threading.Lock())
    config["provider_sources"] = [{"id": "demo", "type": "openai_chat_completions"}]

    await config_service.save_config_async(config, config, is_core=True)

    saved = AstrBotConfig._load_config_dict(str(config_path))
    assert "_runtime_lock" not in saved
    assert saved["provider_sources"][0]["id"] == "demo"


@pytest.mark.asyncio
async def test_plugin_config_does_not_reload_when_save_is_superseded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_config = SimpleNamespace(
        schema={},
        save_config_async=AsyncMock(return_value=False),
    )
    plugin_lifecycle = SimpleNamespace(reload=AsyncMock())
    service = config_service.ConfigFileService(
        SimpleNamespace(
            get_by_name=lambda _name: SimpleNamespace(config=plugin_config)
        ),
        plugin_lifecycle,
    )
    monkeypatch.setattr(
        config_service,
        "validate_config",
        lambda posted, _schema, **_kwargs: ([], posted),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.save_plugin_configs({"enabled": True}, "example-plugin")

    assert exc_info.value.status_code == 409
    plugin_lifecycle.reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_config_does_not_change_runtime_when_save_is_superseded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save = AsyncMock(return_value=False)
    monkeypatch.setattr(config_service, "save_config_async", save)
    platform_manager = SimpleNamespace(
        load_platform=AsyncMock(),
        reload=AsyncMock(),
        terminate_platform=AsyncMock(),
    )
    service = config_service.BotConfigService(
        {
            "platform": [
                {"id": "existing", "type": "webchat", "enable": True},
            ],
        },
        PlatformCatalog(),
        platform_manager,
    )

    with pytest.raises(ApiError) as create_exc:
        await service.create_bot({"id": "new", "type": "webchat", "enable": True})
    with pytest.raises(ApiError) as update_exc:
        await service.update_bot(
            "existing",
            {"id": "existing", "type": "webchat", "enable": False},
        )
    with pytest.raises(ApiError) as delete_exc:
        await service.delete_bot("existing")

    assert create_exc.value.status_code == 409
    assert update_exc.value.status_code == 409
    assert delete_exc.value.status_code == 409
    assert save.await_count == 3
    platform_manager.load_platform.assert_not_awaited()
    platform_manager.reload.assert_not_awaited()
    platform_manager.terminate_platform.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_source_config_does_not_change_runtime_when_save_is_superseded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save = AsyncMock(return_value=False)
    monkeypatch.setattr(config_service, "save_config_async", save)
    runtime_sources = [{"id": "runtime-source"}]
    provider_manager = SimpleNamespace(
        provider_sources_config=runtime_sources,
        reload=AsyncMock(),
        delete_provider=AsyncMock(),
    )
    service = config_service.ProviderConfigService(
        {
            "provider_sources": [
                {
                    "id": "source-a",
                    "type": "openai_chat_completions",
                    "provider_type": "chat_completion",
                },
            ],
            "provider": [
                {"id": "provider-a", "provider_source_id": "source-a"},
            ],
        },
        provider_manager,
        ProviderCatalog(),
        LLMMetadataCatalog(),
    )

    with pytest.raises(ApiError) as create_exc:
        await service.upsert_provider_source(
            "source-new",
            {
                "id": "source-new",
                "type": "openai_chat_completions",
                "provider_type": "chat_completion",
            },
        )
    with pytest.raises(ApiError) as upsert_exc:
        await service.upsert_provider_source(
            "source-a",
            {
                "id": "source-b",
                "type": "openai_chat_completions",
                "provider_type": "chat_completion",
            },
        )
    with pytest.raises(ApiError) as delete_exc:
        await service.delete_provider_source("source-a")

    assert create_exc.value.status_code == 409
    assert upsert_exc.value.status_code == 409
    assert delete_exc.value.status_code == 409
    assert save.await_count == 3
    assert provider_manager.provider_sources_config is runtime_sources
    provider_manager.reload.assert_not_awaited()
    provider_manager.delete_provider.assert_not_awaited()


def _totp_enabled_config() -> dict:
    return {
        "dashboard": {
            "totp": {
                "enable": True,
                "secret": "totp-secret",
                "recovery_code_hash": "recovery-hash",
            }
        },
        "provider_sources": [],
        "provider": [],
        "platform": [],
    }


@pytest.mark.asyncio
async def test_failed_totp_config_persistence_keeps_runtime_rotation_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _totp_enabled_config()
    updated = copy.deepcopy(current)
    updated["dashboard"]["totp"] = {
        "enable": False,
        "secret": "",
        "recovery_code_hash": "",
    }
    state = SimpleNamespace(
        verify_configured_2fa_code=AsyncMock(return_value=True),
        clear_all=AsyncMock(),
    )
    service = config_service.ConfigProfileService(
        SimpleNamespace(confs={"default": current}, default_conf=current),
        SimpleNamespace(),
        SimpleNamespace(reload_pipeline_scheduler=AsyncMock()),
        state,
    )
    monkeypatch.setattr(
        config_service,
        "save_config_async",
        AsyncMock(side_effect=OSError("disk unavailable")),
    )

    with pytest.raises(OSError, match="disk unavailable"):
        await service.update_profile(
            "default",
            updated,
            subject="dashboard-session:one",
            two_factor_code="123456",
        )

    state.verify_configured_2fa_code.assert_awaited_once_with(
        current,
        "123456",
        subject="dashboard-session:one",
        include_pending=True,
        allow_recovery=False,
    )
    state.clear_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_totp_config_persistence_clears_runtime_rotation_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _totp_enabled_config()
    updated = copy.deepcopy(current)
    updated["dashboard"]["totp"] = {
        "enable": False,
        "secret": "",
        "recovery_code_hash": "",
    }
    state = SimpleNamespace(
        verify_configured_2fa_code=AsyncMock(return_value=True),
        clear_all=AsyncMock(),
    )
    core_control = SimpleNamespace(reload_pipeline_scheduler=AsyncMock())
    service = config_service.ConfigProfileService(
        SimpleNamespace(confs={"default": current}, default_conf=current),
        SimpleNamespace(),
        core_control,
        state,
    )
    save = AsyncMock(return_value=True)
    monkeypatch.setattr(config_service, "save_config_async", save)

    await service.update_profile(
        "default",
        updated,
        subject="dashboard-session:one",
        two_factor_code="123456",
    )

    save.assert_awaited_once()
    state.clear_all.assert_awaited_once()
    core_control.reload_pipeline_scheduler.assert_awaited_once_with("default")


@pytest.mark.asyncio
async def test_superseded_totp_config_persistence_keeps_runtime_rotation_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _totp_enabled_config()
    updated = copy.deepcopy(current)
    updated["dashboard"]["totp"] = {
        "enable": False,
        "secret": "",
        "recovery_code_hash": "",
    }
    state = SimpleNamespace(
        verify_configured_2fa_code=AsyncMock(return_value=True),
        clear_all=AsyncMock(),
    )
    core_control = SimpleNamespace(reload_pipeline_scheduler=AsyncMock())
    service = config_service.ConfigProfileService(
        SimpleNamespace(confs={"default": current}, default_conf=current),
        SimpleNamespace(),
        core_control,
        state,
    )
    monkeypatch.setattr(
        config_service,
        "save_config_async",
        AsyncMock(return_value=False),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.update_profile(
            "default",
            updated,
            subject="dashboard-session:one",
            two_factor_code="123456",
        )

    assert exc_info.value.status_code == 409
    state.clear_all.assert_not_awaited()
    core_control.reload_pipeline_scheduler.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_profile_clears_routing_entries_for_deleted_config() -> None:
    acm = SimpleNamespace(delete_conf=AsyncMock(return_value=True))
    ucr = SimpleNamespace(
        umop_to_conf_id={
            "onebot:group:123": "conf-a",
            "onebot:friend:456": "conf-b",
        },
        update_routing_data=AsyncMock(),
    )
    core_control = SimpleNamespace(remove_pipeline_scheduler=AsyncMock())
    service = config_service.ConfigProfileService(
        acm,
        ucr,
        core_control,
        TotpRuntimeState(),
    )

    await service.delete_profile("conf-a")

    acm.delete_conf.assert_awaited_once_with("conf-a")
    core_control.remove_pipeline_scheduler.assert_awaited_once_with("conf-a")
    ucr.update_routing_data.assert_awaited_once_with({"onebot:friend:456": "conf-b"})


@pytest.mark.asyncio
async def test_delete_profile_preserves_more_specific_routes_for_other_profiles() -> (
    None
):
    acm = SimpleNamespace(delete_conf=AsyncMock(return_value=True))
    ucr = SimpleNamespace(
        umop_to_conf_id={
            "::": "conf-a",
            "telegram::": "conf-b",
            "telegram:group:room-*": "conf-b",
            "telegram:group:room-123": "conf-c",
        },
        update_routing_data=AsyncMock(),
    )
    core_control = SimpleNamespace(remove_pipeline_scheduler=AsyncMock())
    service = config_service.ConfigProfileService(
        acm,
        ucr,
        core_control,
        TotpRuntimeState(),
    )

    await service.delete_profile("conf-a")

    core_control.remove_pipeline_scheduler.assert_awaited_once_with("conf-a")
    ucr.update_routing_data.assert_awaited_once_with(
        {
            "telegram::": "conf-b",
            "telegram:group:room-*": "conf-b",
            "telegram:group:room-123": "conf-c",
        }
    )
