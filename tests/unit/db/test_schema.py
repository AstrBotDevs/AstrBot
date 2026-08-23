import ast
import asyncio
import threading
from pathlib import Path

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import OperationalError
from sqlmodel import text

from astrbot.core.db import is_aiosqlite_worker_thread
from astrbot.core.db.schema import (
    _drop_keep_original_alias_column,
    initialize_sqlite_schema,
)
from astrbot.core.db.sqlite import SQLiteDatabase

EXPECTED_TABLE_NAMES = frozenset(
    {
        "api_keys",
        "attachments",
        "auth_audit_log",
        "auth_capabilities",
        "auth_platform_membership_facts",
        "auth_policy_overrides",
        "auth_role_bindings",
        "auth_step_up_credentials",
        "chatui_projects",
        "command_configs",
        "command_conflicts",
        "conversations",
        "cron_jobs",
        "dashboard_accounts",
        "dashboard_trusted_devices",
        "memory_episodes",
        "memory_facts",
        "memory_operation_logs",
        "memory_profiles",
        "memory_scope_policies",
        "memory_tuning_tasks",
        "persona_behavior_policies",
        "persona_expression_assets",
        "persona_folders",
        "persona_jargon_assets",
        "persona_session_states",
        "personas",
        "platform_message_history",
        "platform_sessions",
        "platform_stats",
        "preferences",
        "provider_stats",
        "session_project_relations",
        "umo_aliases",
        "webchat_threads",
    }
)

EXPECTED_TABLE_MODELS = frozenset(
    {
        "ApiKey",
        "Attachment",
        "AuthAuditLog",
        "AuthCapability",
        "AuthPlatformMembershipFact",
        "AuthPolicyOverride",
        "AuthRoleBinding",
        "AuthStepUpCredential",
        "ChatUIProject",
        "CommandConfig",
        "CommandConflict",
        "ConversationV2",
        "CronJob",
        "DashboardAccount",
        "DashboardTrustedDevice",
        "MemoryEpisode",
        "MemoryFact",
        "MemoryOperationLog",
        "MemoryProfile",
        "MemoryScopePolicyRecord",
        "MemoryTuningTask",
        "Persona",
        "PersonaBehaviorPolicy",
        "PersonaExpressionAsset",
        "PersonaFolder",
        "PersonaJargonAsset",
        "PersonaSessionState",
        "PlatformMessageHistory",
        "PlatformSession",
        "PlatformStat",
        "Preference",
        "ProviderStat",
        "SessionProjectRelation",
        "UmoAlias",
        "WebChatThread",
    }
)

REPO_ROOT = Path(__file__).parents[3]
REGISTRY_PATH = REPO_ROOT / "astrbot" / "core" / "db" / "po" / "registry.py"


def _registry_imported_model_names() -> set[str]:
    tree = ast.parse(REGISTRY_PATH.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not node.module.startswith("astrbot.core.db.po."):
            continue
        for alias in node.names:
            if alias.name != "import_all_models":
                names.add(alias.name)
    return names


def _unique_column_sets(sync_conn, table_name: str) -> list[tuple[str, ...]]:
    inspector = sa_inspect(sync_conn)
    uniques = [
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
    ]
    unique_indexes = [
        tuple(index["column_names"])
        for index in inspector.get_indexes(table_name)
        if index.get("unique")
    ]
    return uniques + unique_indexes


def _column_map(sync_conn, table_name: str) -> dict[str, dict]:
    inspector = sa_inspect(sync_conn)
    return {column["name"]: column for column in inspector.get_columns(table_name)}


def _index_names(sync_conn, table_name: str) -> set[str]:
    inspector = sa_inspect(sync_conn)
    return {
        index["name"] for index in inspector.get_indexes(table_name) if index["name"]
    }


def test_registry_explicitly_imports_every_table_model():
    assert _registry_imported_model_names() == EXPECTED_TABLE_MODELS


@pytest.mark.asyncio
async def test_empty_database_creates_expected_tables(temp_db: SQLiteDatabase):
    await temp_db.initialize()

    def table_names(sync_conn) -> set[str]:
        inspector = sa_inspect(sync_conn)
        return {
            name
            for name in inspector.get_table_names()
            if not name.startswith("sqlite_")
        }

    async with temp_db.engine.connect() as conn:
        names = await conn.run_sync(table_names)

    assert names == EXPECTED_TABLE_NAMES


@pytest.mark.asyncio
async def test_platform_message_history_has_required_columns_and_index(
    temp_db: SQLiteDatabase,
):
    await temp_db.initialize()

    def inspect_history(sync_conn) -> tuple[dict[str, dict], set[str]]:
        return (
            _column_map(sync_conn, "platform_message_history"),
            _index_names(sync_conn, "platform_message_history"),
        )

    async with temp_db.engine.connect() as conn:
        columns, indexes = await conn.run_sync(inspect_history)

    assert "role" in columns
    assert "is_group" in columns
    assert "ix_platform_message_history_scope_order" in indexes


@pytest.mark.asyncio
async def test_command_configs_have_unique_command_id(
    temp_db: SQLiteDatabase,
):
    await temp_db.initialize()

    def inspect_commands(sync_conn):
        return (
            _column_map(sync_conn, "command_configs"),
            _column_map(sync_conn, "command_conflicts"),
            _unique_column_sets(sync_conn, "command_configs"),
        )

    async with temp_db.engine.connect() as conn:
        config_columns, conflict_columns, config_uniques = await conn.run_sync(
            inspect_commands
        )

    assert "command_id" in config_columns
    assert config_columns["command_id"]["nullable"] is False
    assert "keep_original_alias" not in config_columns
    assert "command_id" in conflict_columns
    assert ("command_id",) in config_uniques


@pytest.mark.asyncio
async def test_initialize_drops_keep_original_alias_column(
    temp_db: SQLiteDatabase,
):
    await temp_db.initialize()
    async with temp_db.engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE command_configs "
                "ADD COLUMN keep_original_alias BOOLEAN NOT NULL DEFAULT 0"
            )
        )

    await initialize_sqlite_schema(temp_db.engine)

    async with temp_db.engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: _column_map(sync_conn, "command_configs")
        )

    assert "keep_original_alias" not in columns


@pytest.mark.asyncio
async def test_drop_keep_original_alias_swallows_operational_error():
    class BoomConnection:
        async def run_sync(self, fn):
            return True

        async def execute(self, _stmt):
            raise OperationalError("DROP COLUMN", {}, Exception("unsupported"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class BoomEngine:
        def begin(self):
            return BoomConnection()

    await _drop_keep_original_alias_column(BoomEngine())


@pytest.mark.asyncio
async def test_auth_unique_keys_use_non_null_normalized_scope(
    temp_db: SQLiteDatabase,
):
    await temp_db.initialize()

    def inspect_auth(sync_conn):
        binding_columns = _column_map(sync_conn, "auth_role_bindings")
        capability_columns = _column_map(sync_conn, "auth_capabilities")
        return (
            binding_columns,
            capability_columns,
            _unique_column_sets(sync_conn, "auth_role_bindings"),
            _unique_column_sets(sync_conn, "auth_capabilities"),
        )

    async with temp_db.engine.connect() as conn:
        (
            binding_columns,
            capability_columns,
            binding_uniques,
            capability_uniques,
        ) = await conn.run_sync(inspect_auth)

    assert binding_columns["config_id"]["nullable"] is False
    assert capability_columns["config_id"]["nullable"] is False
    assert ("subject_id", "scope_type", "scope_id", "config_id") in binding_uniques
    assert all("role" not in columns for columns in binding_uniques)
    assert (
        "subject_id",
        "action",
        "resource_type",
        "resource_id",
        "config_id",
    ) in capability_uniques


@pytest.mark.asyncio
async def test_wal_and_busy_timeout_are_set(temp_db: SQLiteDatabase):
    await temp_db.initialize()
    async with temp_db.get_db() as session:
        journal_mode = (await session.execute(text("PRAGMA journal_mode"))).scalar()
        busy_timeout = (await session.execute(text("PRAGMA busy_timeout"))).scalar()

    assert journal_mode == "wal"
    assert busy_timeout == 30000


@pytest.mark.asyncio
async def test_initialize_and_get_db_share_one_idempotent_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    calls = 0
    original = initialize_sqlite_schema

    async def counted(engine):
        nonlocal calls
        calls += 1
        await original(engine)

    monkeypatch.setattr("astrbot.core.db.sqlite.initialize_sqlite_schema", counted)
    db = SQLiteDatabase(str(tmp_path / "init-once.db"))

    async def use_session() -> None:
        async with db.get_db() as session:
            await session.execute(text("SELECT 1"))

    try:
        await asyncio.gather(db.initialize(), db.initialize(), use_session())
        assert db.inited is True
        assert calls == 1
        await use_session()
        assert calls == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_close_joins_aiosqlite_worker_threads(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "close-workers.db"))
    await db.initialize()
    async with db.get_db() as session:
        await session.execute(text("SELECT 1"))

    workers = [
        thread for thread in threading.enumerate() if is_aiosqlite_worker_thread(thread)
    ]
    assert workers
    await db.close()
    assert not any(thread.is_alive() for thread in workers)
