"""Keep builtin command identity and the plugin context contract compatible."""

from __future__ import annotations

import importlib
import inspect
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import get_type_hints
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import Provider
from astrbot.core.star import command_management
from astrbot.core.star import context as context_module
from astrbot.core.star import star_manager as loader
from astrbot.core.star.base import Star
from astrbot.core.star.context import Context
from astrbot.core.star.filter.command import CommandFilter, GreedyStr
from astrbot.core.star.filter.permission import PermissionType, PermissionTypeFilter
from astrbot.core.star.star import StarMetadata, star_map, star_registry
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.star.star_tools import StarTools
from astrbot.core.utils.shared_preferences import SharedPreferences

BUILTIN_MODULE = "astrbot.builtin_stars.builtin_commands.main"
NAME_HANDLER_ID = f"{BUILTIN_MODULE}_name"


@pytest.fixture
def builtin_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import the real builtin against registries restored after this test."""
    previous_handlers = list(star_handlers_registry)
    previous_plugins = dict(star_map)
    previous_registry = list(star_registry)
    package = importlib.import_module("astrbot.builtin_stars.builtin_commands")
    previous_module = sys.modules.pop(BUILTIN_MODULE, None)
    monkeypatch.setattr(package, "main", None, raising=False)
    star_handlers_registry.clear()
    star_map.clear()
    star_registry.clear()
    try:
        yield importlib.import_module(BUILTIN_MODULE)
    finally:
        if previous_module is None:
            sys.modules.pop(BUILTIN_MODULE, None)
        else:
            sys.modules[BUILTIN_MODULE] = previous_module
        star_handlers_registry.clear()
        for handler in previous_handlers:
            star_handlers_registry.append(handler)
        star_map.clear()
        star_map.update(previous_plugins)
        star_registry[:] = previous_registry


@pytest.fixture
def builtin_manager(
    builtin_module: ModuleType,
    mock_context: Context,
    database: SQLiteDatabase,
    shared_preferences: SharedPreferences,
    monkeypatch: pytest.MonkeyPatch,
) -> PluginManager:
    """Select one real plugin while keeping storage and imports offline."""
    monkeypatch.setattr(StarTools, "_context", StarTools._context)
    manager = PluginManager(mock_context, mock_context.get_config())
    assert builtin_module.__file__ is not None
    manager.reserved_plugin_path = str(Path(builtin_module.__file__).parent.parent)
    monkeypatch.setattr(
        manager,
        "_get_plugin_modules",
        lambda: [{"module": "main", "pname": "builtin_commands", "reserved": True}],
    )
    monkeypatch.setattr(
        manager,
        "_import_plugin_with_dependency_recovery",
        AsyncMock(return_value=builtin_module),
    )
    monkeypatch.setattr(loader, "sp", shared_preferences)
    monkeypatch.setattr(command_management, "sp", shared_preferences)
    monkeypatch.setattr(command_management, "db_helper", database)
    return manager


async def load_builtin(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch
) -> StarMetadata:
    """Run actual metadata injection and binding without leaking logger cleanup."""
    root_logger = logging.getLogger()
    with monkeypatch.context() as local:
        local.setattr(root_logger, "handlers", root_logger.handlers.copy())
        assert await manager.load(specified_module_path=BUILTIN_MODULE) == (True, None)
    metadata = star_map[BUILTIN_MODULE]
    assert metadata.star_cls is not None
    return metadata


@pytest.mark.asyncio
async def test_name_command_survives_real_metadata_injection_and_reload(
    builtin_manager: PluginManager,
    database: SQLiteDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for alias in ("Engineering Support Room", "Operations Review Room"):
        metadata = await load_builtin(builtin_manager, monkeypatch)
        plugin = metadata.star_cls
        assert plugin.name == "builtin_commands"
        assert callable(getattr(plugin, "set_name", None))
        handler = star_handlers_registry.get_handler_by_full_name(NAME_HANDLER_ID)
        assert handler is not None
        assert handler.handler_name == "name"
        command = next(
            item for item in handler.event_filters if isinstance(item, CommandFilter)
        )
        permission = next(
            item
            for item in handler.event_filters
            if isinstance(item, PermissionTypeFilter)
        )
        assert command.command_name == "name"
        assert command.handler_params == {"alias": GreedyStr}
        assert permission.permission_type is PermissionType.ADMIN
        assert not permission.filter(
            SimpleNamespace(is_admin=lambda: False), builtin_manager.config
        )
        assert permission.filter(
            SimpleNamespace(is_admin=lambda: True), builtin_manager.config
        )
        event = SimpleNamespace(
            unified_msg_origin="test:GroupMessage:engineering",
            message_obj=SimpleNamespace(
                group=SimpleNamespace(group_name="Engineering")
            ),
            get_group_id=lambda: "engineering",
            get_sender_id=lambda: "admin-1",
            get_sender_name=lambda: "Administrator",
            set_result=Mock(),
        )
        arguments = command.validate_and_convert_params(
            alias.split(), command.handler_params
        )
        await handler.handler(event, **arguments)
        saved = await database.get_umo_alias(event.unified_msg_origin)
        assert saved is not None
        assert saved.user_alias == alias
        assert saved.creator_sender_id == "admin-1"
        assert event.set_result.call_args.args[0].use_t2i_ is False


@pytest.mark.asyncio
async def test_name_command_keeps_saved_handler_configuration(
    builtin_manager: PluginManager,
    database: SQLiteDatabase,
    shared_preferences: SharedPreferences,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await shared_preferences.global_put(
        "alter_cmd", {"builtin_commands": {"name": {"permission": "group_admin"}}}
    )
    await database.upsert_command_config(
        NAME_HANDLER_ID,
        "builtin_commands",
        BUILTIN_MODULE,
        "name",
        resolved_command="rename_room",
        enabled=False,
        extra_data={"resolved_aliases": ["room_alias"]},
    )
    await load_builtin(builtin_manager, monkeypatch)
    handler = star_handlers_registry.get_handler_by_full_name(NAME_HANDLER_ID)
    assert handler is not None
    assert handler.enabled is False
    command = next(
        item for item in handler.event_filters if isinstance(item, CommandFilter)
    )
    assert command.command_name == "rename_room"
    assert command.alias == {"room_alias"}
    assert any(
        isinstance(item, PermissionTypeFilter)
        and item.permission_type is PermissionType.GROUP_ADMIN
        for item in handler.event_filters
    )
    stored = await database.get_command_config(NAME_HANDLER_ID)
    assert stored is not None
    assert stored.resolved_command == "rename_room"
    assert stored.enabled is False


@pytest.mark.asyncio
async def test_context_protocol_preserves_async_provider_signature_and_dispatch(
    mock_context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    declared = Star._ContextLike.get_using_provider_async
    assert inspect.iscoroutinefunction(declared)
    assert inspect.signature(declared) == inspect.signature(
        Context.get_using_provider_async
    )
    provider = Mock(spec=Provider)
    resolver = AsyncMock(return_value=provider)
    monkeypatch.setattr(
        mock_context.provider_manager, "get_using_provider_async", resolver
    )
    plugin = Star(mock_context)
    assert (
        await plugin.context.get_using_provider_async("session", locale="en-US")
        is provider
    )
    resolver.assert_awaited_once_with(
        provider_type=ProviderType.CHAT_COMPLETION, umo="session"
    )


@pytest.mark.parametrize(
    ("member", "manager_type"),
    [
        ("conversations", ConversationManager),
        ("conversation_manager", ConversationManager),
        ("message_history_manager", PlatformMessageHistoryManager),
    ],
)
def test_context_protocol_manager_types_match_current_context(
    mock_context: Context, member: str, manager_type: type
) -> None:
    declaration = getattr(Star._ContextLike, member, None)
    assert isinstance(declaration, property)
    assert (
        get_type_hints(declaration.fget, vars(context_module))["return"] is manager_type
    )
    plugin = Star(mock_context)
    assert getattr(plugin.context, member) is getattr(mock_context, member)
    assert plugin.context.conversations is plugin.context.conversation_manager
