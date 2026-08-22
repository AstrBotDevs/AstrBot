import ast
import inspect
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

import pytest

from astrbot.core.db import BaseDatabase
from astrbot.core.db.protocols import (
    ApiKeyStore,
    AttachmentStore,
    ChatProjectSessionStore,
    ChatProjectStore,
    ChatStore,
    CommandStore,
    ConversationStore,
    CronStore,
    DashboardStore,
    DatabaseSessionStore,
    MemoryStore,
    MessageHistoryStore,
    OpenApiStore,
    PersonaRuntimeStore,
    PersonaStore,
    PlatformSessionStore,
    PreferenceStore,
    SessionManagementStore,
    StatisticsSessionStore,
    StatisticsStore,
    UmoAliasStore,
    WebChatStorageStore,
    WebChatThreadStore,
)
from astrbot.core.db.sqlite import SQLiteDatabase

DOMAIN_PROTOCOLS: tuple[type[Protocol], ...] = (
    StatisticsStore,
    PersonaRuntimeStore,
    MemoryStore,
    ConversationStore,
    MessageHistoryStore,
    WebChatThreadStore,
    AttachmentStore,
    ApiKeyStore,
    PersonaStore,
    PreferenceStore,
    CommandStore,
    CronStore,
    PlatformSessionStore,
    UmoAliasStore,
    ChatProjectStore,
)

SQLITE_STORE_PROTOCOLS: tuple[type[Protocol], ...] = (
    DatabaseSessionStore,
    *DOMAIN_PROTOCOLS,
    ChatStore,
    OpenApiStore,
    ChatProjectSessionStore,
    SessionManagementStore,
    StatisticsSessionStore,
    DashboardStore,
    WebChatStorageStore,
)


def _declared_protocol_methods(protocols: Iterable[type[Protocol]]) -> set[str]:
    return {
        name
        for protocol in protocols
        for name, member in vars(protocol).items()
        if not name.startswith("_") and inspect.isfunction(member)
    }


def test_base_database_only_declares_lifecycle_methods():
    domain_methods = _declared_protocol_methods(DOMAIN_PROTOCOLS)

    assert BaseDatabase.__abstractmethods__ == frozenset({"initialize"})
    assert domain_methods.isdisjoint(vars(BaseDatabase))
    assert {"initialize", "get_db", "close"}.issubset(vars(BaseDatabase))


def test_every_sqlite_domain_operation_is_owned_by_a_protocol():
    sqlite_operations = {
        name
        for name, member in inspect.getmembers(
            SQLiteDatabase, inspect.iscoroutinefunction
        )
        if not name.startswith("_")
    }

    assert sqlite_operations == _declared_protocol_methods(DOMAIN_PROTOCOLS) | {
        "close",
        "initialize",
    }


def test_platform_manager_injects_a_narrow_webchat_storage_port():
    """PlatformManager must not take a dependency on SQLiteDatabase."""
    manager_path = (
        Path(__file__).parents[3] / "astrbot" / "core" / "platform" / "manager.py"
    )
    manager_tree = ast.parse(manager_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(manager_tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    database_annotation = next(
        node.annotation
        for node in ast.walk(manager_tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Attribute)
        and isinstance(node.target.value, ast.Name)
        and node.target.value.id == "self"
        and node.target.attr == "database"
    )

    assert "astrbot.core.db.sqlite" not in imported_modules
    assert ast.unparse(database_annotation) == "WebChatStorageStore | None"


@pytest.mark.parametrize("protocol", SQLITE_STORE_PROTOCOLS)
def test_sqlite_database_satisfies_store_contracts(
    temp_db: SQLiteDatabase,
    protocol: type[Protocol],
):
    assert isinstance(temp_db, protocol)
