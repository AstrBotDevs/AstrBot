from __future__ import annotations

import logging
from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from astrbot.core.db.po import ConversationV2
from astrbot.core.provider.entities import ProviderType
from astrbot.core.star.star import PluginRegistry
from astrbot.dashboard.api.sessions import router as sessions_router
from astrbot.dashboard.responses import ApiError, error
from astrbot.dashboard.services.auth_service import DashboardTokenValidator
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
    SessionManagementServiceError,
)
from tests.fixtures.auth import TestAuthorizationService


class _Preferences:
    """In-memory preference seam for SessionManagementService unit tests."""

    def __init__(self) -> None:
        self.session_values: dict[tuple[str, str], Any] = {}
        self.global_values: dict[str, Any] = {}
        self.fail_session_put_for: set[str] = set()
        self.fail_session_remove_for: set[str] = set()
        self.session_put_errors: dict[str, Exception] = {}
        self.session_remove_errors: dict[str, Exception] = {}
        self.global_get_error: Exception | None = None

    async def session_get(self, umo: str, key: str, default: Any = None) -> Any:
        return self.session_values.get((umo, key), default)

    async def session_put(self, umo: str, key: str, value: Any) -> None:
        if error := self.session_put_errors.get(umo):
            raise error
        if umo in self.fail_session_put_for:
            raise RuntimeError(f"cannot save {umo}")
        self.session_values[(umo, key)] = value

    async def session_remove(self, umo: str, key: str) -> None:
        if error := self.session_remove_errors.get(umo):
            raise error
        if umo in self.fail_session_remove_for:
            raise RuntimeError(f"cannot remove {umo}")
        self.session_values.pop((umo, key), None)

    async def clear_async(self, scope: str, scope_id: str) -> None:
        assert scope == "umo"
        if scope_id in self.fail_session_remove_for:
            raise RuntimeError(f"cannot clear {scope_id}")
        for key in [key for key in self.session_values if key[0] == scope_id]:
            del self.session_values[key]

    async def global_get(self, key: str, default: Any = None) -> Any:
        if self.global_get_error is not None:
            raise self.global_get_error
        return self.global_values.get(key, default)

    async def global_put(self, key: str, value: Any) -> None:
        self.global_values[key] = value


class _ProviderManager:
    def __init__(self) -> None:
        self.provider_insts: list[Any] = []
        self.stt_provider_insts: list[Any] = []
        self.tts_provider_insts: list[Any] = []
        self.set_calls: list[tuple[str, ProviderType, str]] = []
        self.clear_calls: list[tuple[str, ProviderType]] = []
        self.clear_all_calls: list[str] = []
        self.fail_set_for: set[str] = set()
        self.fail_clear_for: set[str] = set()
        self.set_errors: dict[str, Exception] = {}

    async def set_provider(
        self,
        *,
        provider_id: str,
        provider_type: ProviderType,
        umo: str,
    ) -> None:
        if error := self.set_errors.get(umo):
            raise error
        if umo in self.fail_set_for:
            raise RuntimeError(f"cannot set provider for {umo}")
        self.set_calls.append((provider_id, provider_type, umo))

    async def clear_provider_override(
        self,
        umo: str,
        provider_type: ProviderType,
    ) -> None:
        if umo in self.fail_clear_for:
            raise RuntimeError(f"cannot clear provider for {umo}")
        self.clear_calls.append((umo, provider_type))

    async def clear_all_provider_overrides(self, umo: str) -> None:
        if umo in self.fail_clear_for:
            raise RuntimeError(f"cannot clear providers for {umo}")
        self.clear_all_calls.append(umo)


def _build_service(temp_db, preferences: _Preferences, providers: _ProviderManager):
    return SessionManagementService(
        temp_db,
        preferences,
        providers,
        SimpleNamespace(personas=[]),
        PluginRegistry(),
        SimpleNamespace(list_kbs=AsyncMock(return_value=[])),
    )


async def _add_conversations(temp_db, umos: Iterable[str]) -> None:
    async with temp_db.get_db() as session:
        async with session.begin():
            for index, umo in enumerate(umos):
                session.add(
                    ConversationV2(
                        conversation_id=f"session-test-{index}",
                        platform_id=umo.split(":", maxsplit=1)[0],
                        user_id=umo,
                        content=[],
                    )
                )


async def _put_rule(temp_db, umo: str, key: str, value: Any) -> None:
    await temp_db.insert_preference_or_update("umo", umo, key, value)


@pytest_asyncio.fixture
async def session_service(temp_db):
    await temp_db.initialize()
    preferences = _Preferences()
    providers = _ProviderManager()
    return _build_service(temp_db, preferences, providers), preferences, providers


@pytest.mark.asyncio
async def test_rules_and_status_tolerate_malformed_preference_values(
    session_service,
    temp_db,
):
    service, _preferences, _providers = session_service
    group_umo = "qq:GroupMessage:team"
    private_umo = "telegram:FriendMessage:alice"
    malformed_fields_umo = "discord:FriendMessage:bad-fields"
    await _add_conversations(temp_db, [group_umo, private_umo, malformed_fields_umo])
    await temp_db.upsert_umo_alias(
        group_umo,
        creator_sender_id="owner",
        auto_name="Team room",
        user_alias="",
    )
    await _put_rule(
        temp_db,
        group_umo,
        "session_service_config",
        {"val": {"custom_name": "Operations", "llm_enabled": False}},
    )
    await _put_rule(
        temp_db,
        group_umo,
        "session_plugin_config",
        {"val": {group_umo: {"disabled_plugins": ["example"]}}},
    )
    await _put_rule(
        temp_db,
        private_umo,
        "session_service_config",
        {"corrupt": "missing val"},
    )
    await _put_rule(
        temp_db,
        private_umo,
        "session_plugin_config",
        {"val": "not a session map"},
    )
    await _put_rule(
        temp_db,
        private_umo,
        "provider_perf_chat_completion",
        {"val": "provider-private"},
    )
    await _put_rule(
        temp_db,
        malformed_fields_umo,
        "session_service_config",
        {"val": {"custom_name": 42, "session_enabled": "disabled"}},
    )

    rules = await service.list_session_rules(page=1, page_size=20, search="")
    no_match_rules = await service.list_session_rules(
        page=1, page_size=20, search="no-match"
    )
    statuses = await service.list_all_umos_with_status(
        page=1,
        page_size=20,
        search="",
        message_type="all",
        platform="",
    )
    no_match_statuses = await service.list_all_umos_with_status(
        page=1,
        page_size=20,
        search="no-match",
        message_type="all",
        platform="",
    )

    rules_by_umo = {item["umo"]: item["rules"] for item in rules["rules"]}
    status_by_umo = {item["umo"]: item for item in statuses["sessions"]}
    assert rules_by_umo[group_umo]["session_service_config"]["custom_name"] == (
        "Operations"
    )
    assert rules_by_umo[group_umo]["session_plugin_config"] == {
        "disabled_plugins": ["example"]
    }
    assert rules_by_umo[private_umo] == {
        "provider_perf_chat_completion": "provider-private"
    }
    assert status_by_umo[group_umo]["llm_enabled"] is False
    assert status_by_umo[private_umo]["session_enabled"] is True
    assert status_by_umo[private_umo]["chat_provider"] == "provider-private"
    assert status_by_umo[malformed_fields_umo]["custom_name"] == ""
    assert status_by_umo[malformed_fields_umo]["session_enabled"] is True
    assert statuses["platforms"] == ["discord", "qq", "telegram"]
    assert no_match_rules["total"] == 0
    assert no_match_statuses["total"] == 0


@pytest.mark.asyncio
async def test_session_scope_alias_search_and_stable_pagination(
    session_service,
    temp_db,
):
    service, preferences, _providers = session_service
    group_umo = "qq:GroupMessage:team"
    private_umo = "qq:FriendMessage:alice"
    second_group_umo = "telegram:group:ops"
    await _add_conversations(temp_db, [second_group_umo, private_umo, group_umo])
    await temp_db.upsert_umo_alias(
        private_umo,
        creator_sender_id="alice-id",
        auto_name="Alice",
        user_alias="VIP Contact",
    )
    await _put_rule(
        temp_db,
        group_umo,
        "session_service_config",
        {"val": {"custom_name": "Team room"}},
    )
    await _put_rule(
        temp_db,
        private_umo,
        "session_service_config",
        {"val": {"custom_name": "Priority user"}},
    )
    preferences.global_values["session_groups"] = {
        "selected": {"name": "Selected", "umos": [private_umo, group_umo]}
    }

    active = await service.list_active_umos()
    by_scope = {
        scope: await service.get_umos_by_scope(scope)
        for scope in ("all", "group", "private")
    }
    custom = await service.get_umos_by_scope("custom_group", "selected")
    searched = await service.list_all_umos_with_status(
        page=0,
        page_size=999,
        search="vip",
        message_type="private",
        platform="qq",
    )
    rules_page = await service.list_session_rules(page=1, page_size=1, search="")

    assert active["umos"] == sorted([group_umo, private_umo, second_group_umo])
    assert (
        next(item for item in active["umo_infos"] if item["umo"] == private_umo)[
            "display_name"
        ]
        == "VIP Contact"
    )
    assert by_scope["all"] == active["umos"]
    assert by_scope["group"] == sorted([group_umo, second_group_umo])
    assert by_scope["private"] == [private_umo]
    assert custom == [private_umo, group_umo]
    assert searched["page"] == 1
    assert searched["page_size"] == 100
    assert searched["total"] == 1
    assert searched["sessions"][0]["umo"] == private_umo
    assert rules_page["total"] == 2
    assert rules_page["rules"][0]["umo"] == sorted([group_umo, private_umo])[0]


@pytest.mark.asyncio
async def test_session_rule_validation_and_provider_override_lifecycle(session_service):
    service, preferences, providers = session_service
    umo = "qq:FriendMessage:alice"

    with pytest.raises(SessionManagementServiceError, match="umo"):
        await service.update_session_rule({"rule_key": "kb_config"})
    with pytest.raises(SessionManagementServiceError, match="不支持"):
        await service.update_session_rule(
            {"umo": umo, "rule_key": "unsupported", "rule_value": {}}
        )
    with pytest.raises(SessionManagementServiceError, match="provider_id"):
        await service.update_session_rule(
            {
                "umo": umo,
                "rule_key": "provider_perf_chat_completion",
                "rule_value": "",
            }
        )
    with pytest.raises(SessionManagementServiceError, match="对象类型"):
        await service.update_session_rule(
            {
                "umo": umo,
                "rule_key": "session_service_config",
                "rule_value": "not a config object",
            }
        )

    await service.update_session_rule(
        {
            "umo": umo,
            "rule_key": "provider_perf_chat_completion",
            "rule_value": "chat-primary",
        }
    )
    await service.update_session_rule(
        {
            "umo": umo,
            "rule_key": "session_plugin_config",
            "rule_value": {"disabled_plugins": ["example"]},
        }
    )
    await service.delete_session_rule(
        {"umo": umo, "rule_key": "provider_perf_chat_completion"}
    )
    await service.delete_session_rule({"umo": umo})

    assert providers.set_calls == [
        ("chat-primary", ProviderType.CHAT_COMPLETION, umo),
    ]
    assert providers.clear_calls == [(umo, ProviderType.CHAT_COMPLETION)]
    assert providers.clear_all_calls == [umo]
    assert preferences.session_values == {}


@pytest.mark.asyncio
async def test_batch_updates_validate_input_and_report_partial_failures(
    session_service,
    caplog: pytest.LogCaptureFixture,
):
    service, preferences, providers = session_service
    good_umo = "qq:FriendMessage:good"
    bad_umo = "qq:FriendMessage:bad"
    sensitive_error = (
        "api_key=session-api-key Bearer session-bearer-token "
        "password=session-password https://internal.example.test/control "
        "/srv/astrbot/secret.txt"
    )
    preferences.session_put_errors[bad_umo] = RuntimeError(sensitive_error)
    providers.set_errors[bad_umo] = RuntimeError(sensitive_error)
    caplog.set_level(logging.ERROR, logger="astrbot")

    with pytest.raises(SessionManagementServiceError, match="数组"):
        await service.batch_update_service({"umos": good_umo, "session_enabled": False})
    with pytest.raises(SessionManagementServiceError, match="数组"):
        await service.batch_update_provider(
            {
                "umos": good_umo,
                "provider_type": "chat_completion",
                "provider_id": "chat-primary",
            }
        )

    service_result = await service.batch_update_service(
        {
            "umos": [good_umo, bad_umo],
            "session_enabled": False,
            "llm_enabled": True,
        }
    )
    provider_result = await service.batch_update_provider(
        {
            "umos": [good_umo, bad_umo],
            "provider_type": "chat_completion",
            "provider_id": "chat-primary",
        }
    )

    assert service_result["success_count"] == 1
    assert service_result["failed_count"] == 1
    assert service_result["failed_umos"] == [bad_umo]
    assert preferences.session_values[(good_umo, "session_service_config")] == {
        "session_enabled": False,
        "llm_enabled": True,
    }
    assert provider_result["success_count"] == 1
    assert provider_result["failed_count"] == 1
    assert provider_result["failed_umos"] == [bad_umo]
    assert providers.set_calls == [
        ("chat-primary", ProviderType.CHAT_COMPLETION, good_umo),
    ]
    for secret in (
        "session-api-key",
        "session-bearer-token",
        "session-password",
        "internal.example.test",
        "/srv/astrbot/secret.txt",
    ):
        assert secret not in caplog.text


@pytest.mark.asyncio
async def test_batch_rule_delete_by_scope_reports_partial_failure_without_secrets(
    session_service,
    caplog: pytest.LogCaptureFixture,
):
    service, preferences, _providers = session_service
    good_umo = "qq:FriendMessage:delete-good"
    bad_umo = "qq:FriendMessage:delete-bad"
    preferences.global_values["session_groups"] = {
        "selected": {"name": "Selected", "umos": [good_umo, bad_umo]}
    }
    preferences.session_values[(good_umo, "session_service_config")] = {
        "session_enabled": False
    }
    preferences.session_values[(bad_umo, "session_service_config")] = {
        "session_enabled": False
    }
    sensitive_error = (
        "api_key=delete-api-key Bearer delete-bearer-token "
        "password=delete-password https://internal.example.test/delete "
        "/srv/astrbot/delete-secret.txt"
    )
    preferences.session_remove_errors[bad_umo] = RuntimeError(sensitive_error)
    caplog.set_level(logging.ERROR, logger="astrbot")

    result = await service.batch_delete_session_rule(
        {
            "scope": "custom_group",
            "group_id": "selected",
            "rule_key": "session_service_config",
        }
    )

    assert result == {
        "message": "已删除 1 条 session_service_config 规则，1 条删除失败",
        "success_count": 1,
        "failed_umos": [bad_umo],
    }
    assert (good_umo, "session_service_config") not in preferences.session_values
    assert (bad_umo, "session_service_config") in preferences.session_values
    for secret in (
        "delete-api-key",
        "delete-bearer-token",
        "delete-password",
        "internal.example.test",
        "/srv/astrbot/delete-secret.txt",
    ):
        assert secret not in caplog.text


@pytest.mark.asyncio
async def test_group_crud_rejects_bad_input_and_skips_corrupt_group_preferences(
    session_service,
    monkeypatch: pytest.MonkeyPatch,
):
    service, preferences, _providers = session_service
    preferences.global_get_error = KeyError("malformed preference")
    assert await service.list_groups() == {"groups": []}
    preferences.global_get_error = None
    preferences.global_values["session_groups"] = {
        "corrupt": "not a group object",
        "existing": {"name": "Existing", "umos": ["u1", "u2"]},
    }
    monkeypatch.setattr(
        "astrbot.dashboard.services.session_management_service.uuid.uuid4",
        lambda: "created-group-id",
    )

    listed = await service.list_groups()
    with pytest.raises(SessionManagementServiceError, match="不能为空"):
        await service.create_group({"name": "  ", "umos": []})
    with pytest.raises(SessionManagementServiceError, match="数组"):
        await service.create_group({"name": "Invalid", "umos": "u3"})
    created = await service.create_group({"name": "New group", "umos": ["u3"]})
    with pytest.raises(SessionManagementServiceError, match="不能为空"):
        await service.update_group({"id": "existing", "name": "  "})
    with pytest.raises(SessionManagementServiceError, match="数组"):
        await service.update_group({"id": "existing", "add_umos": "u3"})
    updated = await service.update_group(
        {
            "id": "existing",
            "add_umos": ["u3", "u1"],
            "remove_umos": ["u2"],
        }
    )
    deleted = await service.delete_group({"id": created["group"]["id"]})

    assert listed == {
        "groups": [
            {
                "id": "existing",
                "name": "Existing",
                "umos": ["u1", "u2"],
                "umo_count": 2,
            }
        ]
    }
    assert created["group"]["id"] == "created-"
    assert updated["group"]["umos"] == ["u1", "u3"]
    assert deleted["message"] == "分组 'New group' 已删除"


def _session_app(
    service: SessionManagementService,
    authorization: object | None = None,
) -> tuple[FastAPI, dict[str, str]]:
    secret = "session-management-service-test-secret"
    validator = DashboardTokenValidator(secret)
    app = FastAPI()
    app.state.dashboard_token_validator = validator
    app.state.services = SimpleNamespace(sessions=service)
    app.state.runtime = SimpleNamespace(
        services=SimpleNamespace(
            authorization=authorization or TestAuthorizationService("data.manage"),
        )
    )

    @app.exception_handler(ApiError)
    async def _api_error_handler(_request, exc: ApiError):
        return JSONResponse(error(exc.message, exc.data), status_code=exc.status_code)

    app.include_router(sessions_router, prefix="/api/v1")
    return app, {"Authorization": f"Bearer {validator.issue('dashboard-user')}"}


class _ConfigBoundAuthorization:
    """Allow only one server-resolved configuration in route tests."""

    def __init__(self, config_id: str) -> None:
        self.config_id = config_id

    async def authorize(self, _subject, _action, resource, _context):
        return SimpleNamespace(
            allowed=resource.config_id == self.config_id,
            requires_step_up=False,
        )


@pytest.mark.asyncio
async def test_session_api_routes_keep_the_standard_envelope(session_service, temp_db):
    service, _preferences, _providers = session_service
    await _add_conversations(temp_db, ["qq:FriendMessage:api-user"])
    app, headers = _session_app(service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        listed = await client.get("/api/v1/sessions", headers=headers)
        invalid_update = await client.patch(
            "/api/v1/sessions/service",
            json={"umos": ["qq:FriendMessage:api-user"]},
            headers=headers,
        )
        created_group = await client.post(
            "/api/v1/session-groups",
            json={"name": "API group", "umos": ["qq:FriendMessage:api-user"]},
            headers=headers,
        )

    assert listed.status_code == 200
    assert listed.json()["status"] == "ok"
    assert listed.json()["data"]["sessions"][0]["umo"] == "qq:FriendMessage:api-user"
    assert invalid_update.status_code == 200
    assert invalid_update.json() == {
        "status": "error",
        "message": "至少需要指定一个要修改的状态",
    }
    assert created_group.status_code == 200
    assert created_group.json()["status"] == "ok"
    assert created_group.json()["data"]["group"]["name"] == "API group"


@pytest.mark.asyncio
async def test_session_mutation_authorizes_the_router_resolved_target_config(
    session_service,
):
    service, preferences, _providers = session_service
    target_umo = "napcat:GroupMessage:config-b-room"
    service.config_router = SimpleNamespace(
        get_conf_id_for_umop=lambda umo: "config-b" if umo == target_umo else None
    )
    app, headers = _session_app(service, _ConfigBoundAuthorization("config-a"))
    headers["X-AstrBot-Config-Id"] = "config-a"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.patch(
            "/api/v1/sessions/service",
            json={"umos": [target_umo], "llm_enabled": False},
            headers=headers,
        )

    assert response.status_code == 403
    assert preferences.session_values == {}
