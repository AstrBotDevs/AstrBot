from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.session import SessionCommands
from astrbot.core.star.filter.permission import ActionPermissionFilter
from astrbot.core.star.register.star_handler import get_handler_declaration
from astrbot.core.star.star_handler import EventType
from astrbot.core.umo_alias import (
    get_event_auto_name,
    normalize_umo_name,
    parse_umo,
    serialize_umo_alias,
)


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


def make_session_context(db) -> SimpleNamespace:
    """Create the narrow session-alias capability used by the command."""

    async def alias(umo: str):
        return await db.get_umo_alias(umo)

    async def set_alias(**kwargs):
        return await db.upsert_umo_alias(**kwargs)

    return SimpleNamespace(
        sessions=SimpleNamespace(alias=alias, set_alias=set_alias),
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
async def test_session_name_saves_group_alias_with_auto_name(temp_db):
    context = make_session_context(temp_db)
    event = make_group_event()

    await SessionCommands(context).name(event, "Backend Room")

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
async def test_session_name_without_alias_shows_current_names(temp_db):
    await temp_db.upsert_umo_alias(
        umo="qq:GroupMessage:1000",
        creator_sender_id="sender-1",
        auto_name="Old Group",
        user_alias="Backend Room",
    )
    context = make_session_context(temp_db)
    event = make_group_event()

    await SessionCommands(context).name(event, "")

    result = event.set_result.call_args.args[0]
    assert result.use_t2i_ is False
    assert result.chain[0].text == "\n".join(
        [
            "Usage: /session name <name>",
            "UMO: qq:GroupMessage:1000",
            "Auto name: Engineering Group",
            "Alias: Backend Room",
        ]
    )


def test_session_name_requires_session_manage_action():
    from astrbot.builtin_stars.builtin_commands.main import Main

    declaration = get_handler_declaration(Main.name, EventType.AdapterMessageEvent)

    assert any(
        isinstance(filter_, ActionPermissionFilter)
        and filter_.action == "session.manage"
        for filter_ in declaration.event_filters
    )


@pytest.mark.parametrize("handler_name", ["reset", "delete"])
def test_conversation_mutations_require_session_manage_action(handler_name: str):
    from astrbot.builtin_stars.builtin_commands.main import Main

    declaration = get_handler_declaration(
        getattr(Main, handler_name),
        EventType.AdapterMessageEvent,
    )

    assert any(
        isinstance(filter_, ActionPermissionFilter)
        and filter_.action == "session.manage"
        for filter_ in declaration.event_filters
    )


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
