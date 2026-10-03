"""Regression coverage for dashboard request narrowing and response contracts."""

from collections.abc import Awaitable
from datetime import datetime, timezone

import pytest

from astrbot.core.db.po import PlatformMessageHistory
from astrbot.dashboard.async_utils import resolve_maybe_awaitable, run_maybe_async
from astrbot.dashboard.services.auth_service import AuthService
from astrbot.dashboard.services.backup_service import BackupService, BackupServiceError
from astrbot.dashboard.services.chat_service import serialize_history_entry
from astrbot.dashboard.services.config_service import ConfigRoutingService
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
    SessionManagementServiceError,
)
from astrbot.dashboard.validation import (
    integer_field,
    is_json_object,
    is_string_list,
    object_path,
    string_field,
    string_list_field,
)


@pytest.mark.parametrize("value", [None, [], "body", 42, {1: "not a JSON key"}])
def test_json_object_rejects_non_objects_and_non_string_keys(value: object) -> None:
    assert not is_json_object(value)


def test_object_validation_preserves_heterogeneous_values() -> None:
    data: dict[str, object] = {"options": {"enabled": False, "count": 0}, "name": ""}
    assert is_json_object(data)
    assert object_path(data, "options") == {"enabled": False, "count": 0}
    assert string_field(data, "name", "default") == ""
    assert integer_field({"count": 0}, "count", 5) == 0
    assert string_list_field({"names": []}, "names") == []
    assert is_string_list(["a", "b"])
    assert not is_string_list(["a", 1])


@pytest.mark.parametrize("value", [[], {}, 42, False])
def test_string_field_uses_the_service_error_boundary(value: object) -> None:
    with pytest.raises(BackupServiceError, match="expected a string"):
        string_field({"filename": value}, "filename", error_type=BackupServiceError)


@pytest.mark.asyncio
async def test_async_bridge_accepts_values_factories_and_nested_awaitables() -> None:
    async def value() -> int:
        return 7

    async def nested() -> Awaitable[int]:
        return value()

    assert await run_maybe_async(7) == 7
    assert await run_maybe_async(lambda: 7) == 7
    assert await run_maybe_async(value) == 7
    assert await resolve_maybe_awaitable(nested()) == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [None, [], {1: "invalid"}])
async def test_invalid_setup_body_keeps_legacy_error_status(body: object) -> None:
    service = AuthService.__new__(AuthService)
    result = await service.complete_setup(body)
    assert result.status == "error"
    assert result.status_code == 200
    assert result.message == "Invalid request payload"
    assert result.jwt_token is None


@pytest.mark.asyncio
async def test_invalid_route_targets_fail_before_persistence() -> None:
    service = ConfigRoutingService.__new__(ConfigRoutingService)
    with pytest.raises(ValueError, match="路由表数据"):
        await service.replace_routes({"routing": {"platform:private:user": {}}})


@pytest.mark.asyncio
async def test_session_target_validation_checks_every_entry() -> None:
    service = SessionManagementService.__new__(SessionManagementService)
    assert await service._target_umos({"umos": ["platform:private:user"]}) == [
        "platform:private:user"
    ]
    with pytest.raises(SessionManagementServiceError, match="字符串数组"):
        await service._target_umos({"umos": ["platform:private:user", {}]})


def test_backup_filename_validation_keeps_traversal_protection() -> None:
    for filename in ([], 42, "../backup.zip", "nested/backup.zip"):
        with pytest.raises(BackupServiceError):
            BackupService._validate_backup_filename(
                filename, missing="Missing filename"
            )
    assert BackupService._validate_backup_filename("backup.zip", missing="missing") == (
        "backup.zip"
    )


def test_history_response_does_not_expose_internal_idempotency_key() -> None:
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    history = PlatformMessageHistory(
        platform_id="webchat",
        user_id="user",
        content={"message": []},
        idempotency_key="internal-retry-token",
        created_at=now,
        updated_at=now,
    )
    result = serialize_history_entry(history)
    assert "idempotency_key" not in result
    assert result["content"] == history.content
    assert result["created_at"] == "2026-09-06T00:00:00+00:00"
    assert history.idempotency_key == "internal-retry-token"
