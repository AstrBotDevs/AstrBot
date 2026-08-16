import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.provider.catalog import ProviderCatalog
from astrbot.core.utils.llm_metadata import LLMMetadataCatalog
from astrbot.core.utils.totp import TotpRuntimeState
from astrbot.dashboard.password_state import (
    set_password_change_required,
    set_password_storage_upgraded,
)
from astrbot.dashboard.server import initialize_dashboard_jwt_secret
from astrbot.dashboard.services import config_service
from astrbot.dashboard.services.auth_service import AuthService
from astrbot.dashboard.services.log_service import LogService, LogServiceError
from astrbot.dashboard.services.subagent_service import (
    SubAgentService,
    SubAgentServiceError,
)
from astrbot.dashboard.services.t2i_service import T2iService, T2iServiceError


class TrackedConfig(dict):
    """In-memory config that records asynchronous persistence calls."""

    def __init__(self, initial: dict, events: list[object]) -> None:
        super().__init__(copy.deepcopy(initial))
        self.events = events

    async def save_config_async(
        self,
        replace_config: dict | None = None,
        *,
        indent: int = 2,
    ) -> bool:
        _ = indent
        self.events.append("persist")
        if replace_config:
            self.clear()
            self.update(copy.deepcopy(replace_config))
        return True


@pytest.mark.asyncio
async def test_password_state_uses_async_config_persistence() -> None:
    events: list[object] = []
    config = TrackedConfig({"dashboard": {}}, events)

    await set_password_change_required(config, True)

    assert config["dashboard"]["password_change_required"] is True
    assert events == ["persist"]


@pytest.mark.asyncio
async def test_password_state_reports_a_superseded_save() -> None:
    events: list[object] = []

    class SupersededConfig(TrackedConfig):
        async def save_config_async(
            self,
            replace_config: dict | None = None,
            *,
            indent: int = 2,
        ) -> bool:
            await super().save_config_async(replace_config, indent=indent)
            return False

    config = SupersededConfig({"dashboard": {}}, events)

    assert await set_password_storage_upgraded(config, True) is False
    assert config["dashboard"]["password_storage_upgraded"] is True
    assert events == ["persist"]


@pytest.mark.asyncio
async def test_setup_does_not_issue_a_token_when_config_save_is_superseded() -> None:
    events: list[object] = []

    class SupersededConfig(TrackedConfig):
        async def save_config_async(
            self,
            replace_config: dict | None = None,
            *,
            indent: int = 2,
        ) -> bool:
            _ = replace_config, indent
            self.events.append("persist")
            return False

    initial_dashboard_config = {
        "jwt_secret": "test-jwt-secret",
        "username": "astrbot",
        "password": "",
        "pbkdf2_password": "",
        "password_storage_upgraded": False,
        "password_change_required": True,
    }
    config = SupersededConfig({"dashboard": initial_dashboard_config}, events)
    service = AuthService(
        SimpleNamespace(),
        config,
        demo_mode=False,
        totp_runtime_state=TotpRuntimeState(),
    )

    result = await service.complete_setup(
        {
            "username": "astrbot-admin",
            "password": "AstrbotSecure123!",
            "confirm_password": "AstrbotSecure123!",
        }
    )

    assert result.status == "error"
    assert result.status_code == 409
    assert result.jwt_token is None
    assert config["dashboard"] == initial_dashboard_config
    assert events == ["persist"]


@pytest.mark.asyncio
async def test_dashboard_jwt_secret_is_persisted_asynchronously_before_use() -> None:
    events: list[object] = []
    config = TrackedConfig({"dashboard": {"jwt_secret": ""}}, events)

    secret = await initialize_dashboard_jwt_secret(config)

    assert secret == config["dashboard"]["jwt_secret"]
    assert len(secret) == 64
    assert events == ["persist"]


@pytest.mark.asyncio
async def test_dashboard_jwt_secret_rolls_back_when_async_persistence_fails() -> None:
    events: list[object] = []

    class FailingConfig(TrackedConfig):
        async def save_config_async(
            self,
            replace_config: dict | None = None,
            *,
            indent: int = 2,
        ) -> bool:
            _ = replace_config, indent
            self.events.append("persist")
            raise OSError("disk unavailable")

    config = FailingConfig({"dashboard": {"jwt_secret": ""}}, events)

    with pytest.raises(OSError, match="disk unavailable"):
        await initialize_dashboard_jwt_secret(config)

    assert config["dashboard"]["jwt_secret"] == ""
    assert events == ["persist"]


@pytest.mark.asyncio
async def test_dashboard_jwt_secret_is_not_used_when_save_is_superseded() -> None:
    events: list[object] = []

    class SupersededConfig(TrackedConfig):
        async def save_config_async(
            self,
            replace_config: dict | None = None,
            *,
            indent: int = 2,
        ) -> bool:
            _ = replace_config, indent
            self.events.append("persist")
            return False

    config = SupersededConfig({"dashboard": {"jwt_secret": ""}}, events)

    with pytest.raises(RuntimeError, match="JWT secret initialization was superseded"):
        await initialize_dashboard_jwt_secret(config)

    assert config["dashboard"]["jwt_secret"] == ""
    assert events == ["persist"]


@pytest.mark.asyncio
async def test_log_settings_use_async_config_persistence() -> None:
    events: list[object] = []
    config = TrackedConfig({"trace_enable": False}, events)
    service = LogService(SimpleNamespace(), config)

    message = await service.update_trace_settings(True)

    assert message == "Trace 设置已更新"
    assert config["trace_enable"] is True
    assert events == ["persist"]


@pytest.mark.asyncio
async def test_log_settings_do_not_report_success_when_save_is_superseded() -> None:
    events: list[object] = []

    class SupersededConfig(TrackedConfig):
        async def save_config_async(
            self,
            replace_config: dict | None = None,
            *,
            indent: int = 2,
        ) -> bool:
            await super().save_config_async(replace_config, indent=indent)
            return False

    service = LogService(
        SimpleNamespace(), SupersededConfig({"trace_enable": False}, events)
    )

    with pytest.raises(LogServiceError, match="superseded"):
        await service.update_trace_settings(True)

    assert events == ["persist"]


@pytest.mark.asyncio
async def test_subagent_config_persists_before_runtime_reload() -> None:
    events: list[object] = []
    config = TrackedConfig({"subagent_orchestrator": {}}, events)

    async def reload_from_config(data: dict) -> None:
        events.append(("reload", copy.deepcopy(data)))

    await SubAgentService(
        config,
        SimpleNamespace(reload_from_config=reload_from_config),
        SimpleNamespace(),
    ).update_config({"agents": []})

    assert events == ["persist", ("reload", {"agents": []})]


@pytest.mark.asyncio
async def test_subagent_config_does_not_reload_when_save_is_superseded() -> None:
    events: list[object] = []

    class SupersededConfig(TrackedConfig):
        async def save_config_async(
            self,
            replace_config: dict | None = None,
            *,
            indent: int = 2,
        ) -> bool:
            await super().save_config_async(replace_config, indent=indent)
            return False

    config = SupersededConfig({"subagent_orchestrator": {}}, events)
    reload_from_config = AsyncMock()
    service = SubAgentService(
        config,
        SimpleNamespace(reload_from_config=reload_from_config),
        SimpleNamespace(),
    )

    with pytest.raises(SubAgentServiceError, match="superseded"):
        await service.update_config({"agents": []})

    assert events == ["persist"]
    reload_from_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_t2i_configurations_persist_before_scheduler_reload() -> None:
    events: list[object] = []
    first = TrackedConfig({"t2i_active_template": "base"}, events)
    second = TrackedConfig({"t2i_active_template": "base"}, events)

    async def reload_pipeline_scheduler(config_id: str) -> None:
        events.append(("reload", config_id))

    config_manager = SimpleNamespace(confs={"first": first, "second": second})
    control = SimpleNamespace(reload_pipeline_scheduler=reload_pipeline_scheduler)

    await T2iService(
        first,
        config_manager,
        control,
        manager=SimpleNamespace(),
    ).sync_active_template_to_all_configs("cinematic")

    assert first["t2i_active_template"] == "cinematic"
    assert second["t2i_active_template"] == "cinematic"
    assert events == [
        "persist",
        "persist",
        ("reload", "first"),
        ("reload", "second"),
    ]


@pytest.mark.asyncio
async def test_t2i_does_not_reload_schedulers_when_save_is_superseded() -> None:
    events: list[object] = []

    class SupersededConfig(TrackedConfig):
        async def save_config_async(
            self,
            replace_config: dict | None = None,
            *,
            indent: int = 2,
        ) -> bool:
            await super().save_config_async(replace_config, indent=indent)
            return False

    config = SupersededConfig({"t2i_active_template": "base"}, events)
    reload_pipeline_scheduler = AsyncMock()
    config_manager = SimpleNamespace(confs={"first": config})
    control = SimpleNamespace(reload_pipeline_scheduler=reload_pipeline_scheduler)

    service = T2iService(
        config,
        config_manager,
        control,
        manager=SimpleNamespace(),
    )
    with pytest.raises(T2iServiceError, match="superseded"):
        await service.sync_active_template_to_all_configs("cinematic")

    assert events == ["persist"]
    reload_pipeline_scheduler.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_source_deletion_persists_before_runtime_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    config = TrackedConfig(
        {
            "provider_sources": [{"id": "source-a"}],
            "provider": [],
        },
        events,
    )

    async def persist(
        next_config: dict,
        live_config: TrackedConfig,
        *,
        is_core: bool,
    ) -> bool:
        _ = is_core
        events.append("persist")
        live_config.clear()
        live_config.update(copy.deepcopy(next_config))
        return True

    async def delete_provider(*, provider_source_id: str) -> None:
        events.append(("delete", provider_source_id))

    monkeypatch.setattr(config_service, "save_config_async", persist)
    manager = SimpleNamespace(
        delete_provider=delete_provider,
        provider_sources_config=config["provider_sources"],
    )
    service = config_service.ProviderConfigService(
        config,
        manager,
        ProviderCatalog(),
        LLMMetadataCatalog(),
    )

    await service.delete_provider_source("source-a")

    assert config["provider_sources"] == []
    assert events == ["persist", ("delete", "source-a")]
