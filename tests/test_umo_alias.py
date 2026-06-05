import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.name import NameCommand
from astrbot.core.star.filter.permission import PermissionType, PermissionTypeFilter
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.umo_alias import (
    get_event_auto_name,
    normalize_umo_name,
    parse_umo,
    serialize_umo_alias,
)

BUILTIN_COMMANDS_PACKAGE = "astrbot.builtin_stars.builtin_commands"
BUILTIN_MAIN_MODULE = f"{BUILTIN_COMMANDS_PACKAGE}.main"


def make_group_event() -> SimpleNamespace:
    return SimpleNamespace(
        unified_msg_origin="qq:GroupMessage:1000",
        message_obj=SimpleNamespace(
            group=SimpleNamespace(group_name="Engineering Group")
        ),
        get_group_id=lambda: "1000",
        get_sender_id=lambda: "sender-1",
        get_sender_name=lambda: "Alice",
        set_result=MagicMock(),
    )


@pytest.mark.asyncio
async def test_umo_alias_upsert_updates_existing_record(temp_db):
    created = await temp_db.upsert_umo_alias(
        umo="qq:GroupMessage:1000",
        creator_sender_id="sender-1",
        auto_name="Old Group",
        user_alias="Old Alias",
    )

    updated = await temp_db.upsert_umo_alias(
        umo="qq:GroupMessage:1000",
        creator_sender_id="sender-2",
        auto_name="New Group",
        user_alias="New Alias",
    )

    assert created.id == updated.id
    assert updated.creator_sender_id == "sender-2"
    assert updated.auto_name == "New Group"
    assert updated.user_alias == "New Alias"

    fetched = await temp_db.get_umo_alias("qq:GroupMessage:1000")
    assert fetched is not None
    assert serialize_umo_alias(fetched, fetched.umo)["display_name"] == "New Alias"


@pytest.mark.asyncio
async def test_name_command_saves_group_alias_with_auto_name(temp_db):
    context = SimpleNamespace(get_db=lambda: temp_db)
    event = make_group_event()

    await NameCommand(context).name(event, "Backend Room")

    alias = await temp_db.get_umo_alias("qq:GroupMessage:1000")
    assert alias is not None
    assert alias.creator_sender_id == "sender-1"
    assert alias.auto_name == "Engineering Group"
    assert alias.user_alias == "Backend Room"

    result = event.set_result.call_args.args[0]
    assert result.use_t2i_ is False
    assert result.chain[0].text == (
        "UMO name set to: Backend Room\nUMO: qq:GroupMessage:1000"
    )


@pytest.mark.asyncio
async def test_name_command_without_alias_shows_current_names(temp_db):
    await temp_db.upsert_umo_alias(
        umo="qq:GroupMessage:1000",
        creator_sender_id="sender-1",
        auto_name="Old Group",
        user_alias="Backend Room",
    )
    context = SimpleNamespace(get_db=lambda: temp_db)
    event = make_group_event()

    await NameCommand(context).name(event, "")

    result = event.set_result.call_args.args[0]
    assert result.use_t2i_ is False
    assert result.chain[0].text == "\n".join(
        [
            "Usage: /name <name>",
            "UMO: qq:GroupMessage:1000",
            "Auto name: Engineering Group",
            "Alias: Backend Room",
        ]
    )


def test_name_command_requires_admin_permission():
    missing_package_attr = object()
    original_handlers = list(star_handlers_registry)
    original_module = sys.modules.get(BUILTIN_MAIN_MODULE)
    commands_package = sys.modules.get(BUILTIN_COMMANDS_PACKAGE)
    original_package_main = (
        getattr(commands_package, "main", missing_package_attr)
        if commands_package
        else missing_package_attr
    )
    try:
        star_handlers_registry.clear()
        sys.modules.pop(BUILTIN_MAIN_MODULE, None)
        reloaded_main = importlib.import_module(BUILTIN_MAIN_MODULE)
        handler = star_handlers_registry.get_handler_by_full_name(
            f"{reloaded_main.Main.name.__module__}_{reloaded_main.Main.name.__name__}"
        )

        assert handler is not None
        assert any(
            isinstance(filter_, PermissionTypeFilter)
            and filter_.permission_type == PermissionType.ADMIN
            for filter_ in handler.event_filters
        )
    finally:
        if original_module is None:
            sys.modules.pop(BUILTIN_MAIN_MODULE, None)
        else:
            sys.modules[BUILTIN_MAIN_MODULE] = original_module
        commands_package = sys.modules.get(BUILTIN_COMMANDS_PACKAGE)
        if commands_package:
            if original_package_main is missing_package_attr:
                if hasattr(commands_package, "main"):
                    delattr(commands_package, "main")
            else:
                commands_package.main = original_package_main
        star_handlers_registry.clear()
        for handler in original_handlers:
            star_handlers_registry.append(handler)


def test_umo_name_helpers_accept_numeric_ids():
    assert normalize_umo_name(123456) == "123456"
    assert (
        get_event_auto_name(
            SimpleNamespace(
                message_obj=SimpleNamespace(group=SimpleNamespace(group_name=None)),
                get_group_id=lambda: 123456,
                get_sender_id=lambda: 789,
                get_sender_name=lambda: "",
            )
        )
        == "123456"
    )


def test_parse_umo_handles_empty_values():
    assert parse_umo(None) == {
        "platform": "unknown",
        "message_type": "unknown",
        "session_id": "",
    }
    assert parse_umo("qq:GroupMessage:1000:extra") == {
        "platform": "qq",
        "message_type": "GroupMessage",
        "session_id": "1000:extra",
    }
