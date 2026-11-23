"""Regressions for dashboard validation and persistence boundaries."""

from collections.abc import Awaitable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio

import astrbot.core.session_overrides as session_overrides
import astrbot.dashboard.services.session_management_service as session_management
from astrbot.core import LogBroker
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config_bindings import BINDING_KEY
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.utils.shared_preferences import SharedPreferences
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

UMO = "fixture:FriendMessage:kept"
OTHER_UMO = "fixture:FriendMessage:other"
KEEP_GROUP = {"kept-group": {"name": "Keep", "umos": [UMO]}}


async def _preference_rows(database: SQLiteDatabase) -> list[dict[str, object]]:
    records = await database.get_preferences()
    return [
        record.model_dump()
        for record in sorted(
            records, key=lambda row: (row.scope, row.scope_id, row.key)
        )
    ]


@pytest_asyncio.fixture
async def boundary_core(
    astrbot_config: AstrBotConfig,
    database: SQLiteDatabase,
    shared_preferences: SharedPreferences,
    monkeypatch: pytest.MonkeyPatch,
) -> AstrBotCoreLifecycle:
    """Use real configuration, routing, and SQLite without starting the bot."""
    router = UmopConfigRouter(shared_preferences)
    await router.initialize()
    core = AstrBotCoreLifecycle(LogBroker(), database)
    core.astrbot_config = astrbot_config
    core.umop_config_router = router
    core.astrbot_config_mgr = AstrBotConfigManager(
        astrbot_config, router, shared_preferences
    )
    monkeypatch.setattr(session_management, "sp", shared_preferences)
    monkeypatch.setattr(session_overrides, "sp", shared_preferences)
    return core


@pytest_asyncio.fixture
async def session_service(
    boundary_core: AstrBotCoreLifecycle,
    database: SQLiteDatabase,
    shared_preferences: SharedPreferences,
) -> SessionManagementService:
    service = SessionManagementService(boundary_core, database)
    await shared_preferences.session_put(
        UMO,
        BINDING_KEY,
        {
            "profile_id": "keep-profile",
            "overrides": {"provider_settings.enable": False},
        },
    )
    await service.save_groups(deepcopy(KEEP_GROUP))
    return service


@pytest.mark.parametrize("value", [None, [], "body", 42, {1: "not a JSON key"}])
def test_json_object_rejects_non_objects_and_non_string_keys(value: object) -> None:
    assert not is_json_object(value)


def test_object_validation_preserves_falsey_and_heterogeneous_values() -> None:
    data = {"options": {"enabled": False, "count": 0}, "name": ""}
    before = deepcopy(data)
    assert is_json_object(data)
    assert object_path(data, "options") == {"enabled": False, "count": 0}
    assert string_field(data, "name", "fallback") == ""
    assert integer_field({"count": 0}, "count", 5) == 0
    assert string_list_field({"names": []}, "names") == []
    assert string_list_field({}, "names") is None
    assert is_string_list(["a", "b"])
    assert not is_string_list(["a", 1])
    assert data == before


@pytest.mark.parametrize("options", [None, [], False, {1: "invalid key"}])
def test_object_path_rejects_invalid_nested_objects(options: object) -> None:
    with pytest.raises(ValueError, match="options"):
        object_path({"options": options}, "options")


@pytest.mark.parametrize("value", [[], {}, 42, False])
def test_string_field_uses_the_service_error_boundary(value: object) -> None:
    with pytest.raises(BackupServiceError, match="expected a string"):
        string_field({"filename": value}, "filename", error_type=BackupServiceError)


@pytest.mark.parametrize("value", [None, [], {}, "0", 1.5])
def test_integer_field_rejects_values_without_coercing(value: object) -> None:
    with pytest.raises(BackupServiceError, match="expected an integer"):
        integer_field({"count": value}, "count", 5, error_type=BackupServiceError)


@pytest.mark.asyncio
async def test_async_bridge_resolves_each_factory_and_nested_awaitable_once() -> None:
    calls = []

    def value() -> int:
        calls.append("value")
        return 7

    async def nested() -> Awaitable[int]:
        calls.append("nested")

        async def leaf() -> int:
            calls.append("leaf")
            return 11

        return leaf()

    assert await run_maybe_async(7) == 7
    assert await run_maybe_async(value) == 7
    assert await run_maybe_async(nested) == 11
    assert calls == ["value", "nested", "leaf"]
    assert await resolve_maybe_awaitable(nested()) == 11
    assert calls == ["value", "nested", "leaf", "nested", "leaf"]


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [None, [], {1: "invalid"}])
async def test_invalid_setup_body_preserves_status_and_storage(
    body: object, astrbot_config: AstrBotConfig, database: SQLiteDatabase
) -> None:
    service = AuthService(database, astrbot_config, demo_mode=False)
    before_config = deepcopy(dict(astrbot_config))
    config_file = Path(astrbot_config.config_path)
    before_file = config_file.read_bytes()
    before_rows = await _preference_rows(database)

    result = await service.complete_setup(body)

    assert result.status == "error"
    assert result.status_code == 200
    assert result.message == "Invalid request payload"
    assert result.jwt_token is None
    assert dict(astrbot_config) == before_config
    assert config_file.read_bytes() == before_file
    assert await _preference_rows(database) == before_rows


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"routing": []},
        {"routing": {1: "profile"}},
        {"routing": {UMO: {}}},
        {"routing": {OTHER_UMO: "valid-profile", UMO: False}},
    ],
)
async def test_invalid_route_targets_fail_before_memory_or_sqlite_changes(
    boundary_core: AstrBotCoreLifecycle, database: SQLiteDatabase, payload: object
) -> None:
    service = ConfigRoutingService(boundary_core)
    await service.replace_routes({"routing": {UMO: "keep-profile"}})
    before_rows = await _preference_rows(database)

    with pytest.raises(ValueError, match="路由表数据"):
        await service.replace_routes(payload)

    assert service.list_routes() == {"routing": {UMO: "keep-profile"}}
    assert await _preference_rows(database) == before_rows


@pytest.mark.asyncio
async def test_valid_route_replacement_survives_router_reload(
    boundary_core: AstrBotCoreLifecycle, shared_preferences: SharedPreferences
) -> None:
    mapping = {UMO: "profile-one", OTHER_UMO: "profile-two"}
    await ConfigRoutingService(boundary_core).replace_routes({"routing": mapping})
    reloaded = UmopConfigRouter(shared_preferences)
    await reloaded.initialize()
    assert reloaded.umop_to_conf_id == mapping


@pytest.mark.asyncio
@pytest.mark.parametrize("umos", [[UMO, {}], [UMO, None], [UMO, 42], UMO, {}, False])
async def test_invalid_batch_delete_targets_do_not_remove_valid_earlier_entries(
    session_service: SessionManagementService,
    database: SQLiteDatabase,
    umos: object,
) -> None:
    before_rows = await _preference_rows(database)
    with pytest.raises(SessionManagementServiceError, match="umos"):
        await session_service.batch_delete_session_rule({"umos": umos})
    assert await _preference_rows(database) == before_rows


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "field"),
    [
        ("create_group", "umos"),
        ("update_group", "umos"),
        ("update_group", "add_umos"),
        ("update_group", "remove_umos"),
    ],
)
@pytest.mark.parametrize("value", [[UMO, {}], {}, False])
async def test_invalid_group_targets_are_rejected_before_any_persistence(
    session_service: SessionManagementService,
    database: SQLiteDatabase,
    operation: str,
    field: str,
    value: object,
) -> None:
    payload = {"id": "kept-group", "name": "Changed", field: value}
    before_payload = deepcopy(payload)
    before_rows = await _preference_rows(database)

    with pytest.raises(SessionManagementServiceError, match="list of strings"):
        await getattr(session_service, operation)(payload)

    assert payload == before_payload
    assert await session_service.get_groups() == KEEP_GROUP
    assert await _preference_rows(database) == before_rows


@pytest.mark.asyncio
async def test_valid_session_batch_delete_removes_only_targeted_override(
    session_service: SessionManagementService, shared_preferences: SharedPreferences
) -> None:
    await shared_preferences.session_put(
        OTHER_UMO, BINDING_KEY, {"profile_id": "other"}
    )

    result = await session_service.batch_delete_session_rule({"umos": [UMO]})

    assert result["success_count"] == 1
    assert "failed_umos" not in result
    assert await shared_preferences.session_get(UMO, BINDING_KEY) == {
        "profile_id": "keep-profile",
        "overrides": {},
    }
    assert await shared_preferences.session_get(OTHER_UMO, BINDING_KEY) == {
        "profile_id": "other"
    }
    assert await session_service.get_groups() == KEEP_GROUP


@pytest.mark.asyncio
async def test_group_updates_preserve_valid_targets_and_accept_explicit_empty_list(
    session_service: SessionManagementService,
) -> None:
    created = await session_service.create_group({"name": "New", "umos": [UMO]})
    group_id = created["group"]["id"]
    updated = await session_service.update_group(
        {"id": group_id, "add_umos": [OTHER_UMO], "remove_umos": [UMO]}
    )
    assert updated["group"]["umos"] == [OTHER_UMO]
    assert updated["group"]["umo_count"] == 1
    cleared = await session_service.update_group({"id": group_id, "umos": []})
    assert cleared["group"]["umos"] == []
    assert cleared["group"]["umo_count"] == 0
    groups = await session_service.get_groups()
    assert groups["kept-group"] == KEEP_GROUP["kept-group"]
    assert groups[group_id] == {"name": "New", "umos": []}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename", [None, [], 42, "../outside.zip", "nested/backup.zip", "..\\outside.zip"]
)
async def test_backup_filename_rejection_leaves_real_files_untouched(
    boundary_core: AstrBotCoreLifecycle,
    database: SQLiteDatabase,
    tmp_path: Path,
    filename: object,
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    inside = backup_dir / "backup.zip"
    outside = tmp_path / "outside.zip"
    inside.write_bytes(b"inside-backup")
    outside.write_bytes(b"outside-backup")
    service = BackupService(database, boundary_core)
    service.backup_dir = str(backup_dir)

    with pytest.raises(BackupServiceError):
        service.delete_backup({"filename": filename})

    assert inside.read_bytes() == b"inside-backup"
    assert outside.read_bytes() == b"outside-backup"
    assert sorted(path.name for path in backup_dir.iterdir()) == ["backup.zip"]


@pytest.mark.asyncio
async def test_persisted_history_keeps_internal_key_out_of_public_response(
    database: SQLiteDatabase,
) -> None:
    timestamp = datetime(2026, 9, 6, tzinfo=UTC)
    record = PlatformMessageHistory(
        platform_id="webchat",
        user_id="user",
        content={"message": [{"type": "plain", "text": "visible"}]},
        idempotency_key="internal-retry-token",
        created_at=timestamp,
        updated_at=timestamp,
    )
    async with database.get_db() as session:
        async with session.begin():
            session.add(record)
            await session.flush()
            record_id = record.id
    assert record_id is not None
    async with database.get_db() as session:
        persisted = await session.get(PlatformMessageHistory, record_id)
        assert persisted is not None
        before = persisted.model_dump()
        assert before["idempotency_key"] == "internal-retry-token"

        result = serialize_history_entry(persisted)

        assert "idempotency_key" not in result
        assert result["id"] == record_id
        assert result["content"] == before["content"]
        assert datetime.fromisoformat(result["created_at"]) == timestamp
        assert datetime.fromisoformat(result["updated_at"]) == timestamp
        assert persisted.model_dump() == before
    async with database.get_db() as session:
        unchanged = await session.get(PlatformMessageHistory, record_id)
        assert unchanged is not None
        assert unchanged.idempotency_key == "internal-retry-token"
