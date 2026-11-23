"""Command edits persist exact state and immediately update runtime filters."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.db.po import CommandConfig
from astrbot.core.star import command_management as management
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    StarHandlerRegistry,
)


@pytest.fixture
def commands(monkeypatch):
    registry, plugins, records = StarHandlerRegistry(), {}, {}

    async def upsert(**values):
        record = CommandConfig(**values)
        records[record.handler_full_name] = record
        return record

    async def delete(names):
        for name in names:
            records.pop(name)

    database = SimpleNamespace(
        get_command_configs=AsyncMock(side_effect=lambda: list(records.values())),
        get_command_config=AsyncMock(side_effect=records.get),
        upsert_command_config=AsyncMock(side_effect=upsert),
        delete_command_configs=AsyncMock(side_effect=delete),
    )
    monkeypatch.setattr(management, "db_helper", database)
    monkeypatch.setattr(management, "star_handlers_registry", registry)
    monkeypatch.setattr(management, "star_map", plugins)

    def add(name, *, command_name=None, activated=True):
        async def handler(self, event):
            return name

        module = f"data.plugins.{name}.main"
        metadata = StarHandlerMetadata(
            EventType.AdapterMessageEvent,
            f"{module}_command",
            "command",
            module,
            handler,
            [],
        )
        metadata.event_filters.append(
            CommandFilter(command_name or name, handler_md=metadata)
        )
        registry.append(metadata)
        plugins[module] = StarMetadata(
            name=name, module_path=module, activated=activated
        )
        return metadata

    return SimpleNamespace(add=add, records=records, db=database)


@pytest.mark.asyncio
async def test_toggle_persists_and_updates_only_the_selected_command(commands):
    selected, other = commands.add("selected"), commands.add("other")
    descriptor = await management.toggle_command(selected.handler_full_name, False)
    assert descriptor.enabled is False
    assert selected.enabled is False
    assert other.enabled is True
    record = commands.records[selected.handler_full_name]
    assert record.enabled is False
    assert record.original_command == record.resolved_command == "selected"
    commands.db.upsert_command_config.assert_awaited_once()
    commands.db.delete_command_configs.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_rebuilds_cached_names_and_aliases(commands):
    selected = commands.add("selected")
    command_filter = selected.event_filters[0]
    assert command_filter.get_complete_command_names() == ["selected"]
    descriptor = await management.rename_command(
        selected.handler_full_name, " renamed ", aliases=["short"]
    )
    assert descriptor.original_command == "selected"
    assert descriptor.effective_command == "renamed"
    assert descriptor.aliases == ["short"]
    assert set(command_filter.get_complete_command_names()) == {"renamed", "short"}
    record = commands.records[selected.handler_full_name]
    assert record.resolved_command == "renamed"
    assert record.extra_data["resolved_aliases"] == ["short"]
    assert record.resolution_strategy == "manual_rename"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("new_name", "aliases"), [("", []), ("occupied", []), ("free", ["occupied"])]
)
async def test_invalid_or_conflicting_rename_does_not_write(
    commands, new_name, aliases
):
    selected = commands.add("selected")
    commands.add("other", command_name="occupied")
    with pytest.raises(ValueError):
        await management.rename_command(selected.handler_full_name, new_name, aliases)
    commands.db.upsert_command_config.assert_not_awaited()
    assert selected.event_filters[0].command_name == "selected"


@pytest.mark.asyncio
async def test_missing_command_is_rejected_before_database_access(commands):
    with pytest.raises(ValueError):
        await management.toggle_command("missing", False)
    commands.db.get_command_config.assert_not_awaited()
    commands.db.upsert_command_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_removes_only_stale_persistent_records(commands):
    live = commands.add("live")
    await management.toggle_command(live.handler_full_name, False)
    commands.records["removed"] = CommandConfig(
        handler_full_name="removed",
        plugin_name="gone",
        module_path="gone",
        original_command="gone",
        enabled=True,
    )
    await management.sync_command_configs()
    commands.db.delete_command_configs.assert_awaited_once_with(["removed"])
    assert set(commands.records) == {live.handler_full_name}
    assert live.enabled is False


@pytest.mark.asyncio
async def test_listing_sorts_commands_and_excludes_inactive_plugins_from_conflicts(
    commands,
):
    first = commands.add("first", command_name="shared")
    second = commands.add("second", command_name="shared")
    inactive = commands.add("inactive", command_name="shared", activated=False)
    commands.add("alpha")
    listed = await management.list_commands()
    assert [item["effective_command"] for item in listed] == [
        "alpha",
        "shared",
        "shared",
        "shared",
    ]
    by_name = {item["handler_full_name"]: item for item in listed}
    assert by_name[first.handler_full_name]["has_conflict"] is True
    assert by_name[second.handler_full_name]["has_conflict"] is True
    assert by_name[inactive.handler_full_name]["has_conflict"] is False
    assert by_name[inactive.handler_full_name]["plugin_activated"] is False
    assert await management.list_command_conflicts() == [
        {
            "conflict_key": "shared",
            "handlers": [
                {
                    "handler_full_name": first.handler_full_name,
                    "plugin": "first",
                    "current_name": "shared",
                },
                {
                    "handler_full_name": second.handler_full_name,
                    "plugin": "second",
                    "current_name": "shared",
                },
            ],
        }
    ]
