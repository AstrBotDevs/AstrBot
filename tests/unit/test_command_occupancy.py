"""Exclusive public-path occupancy for command catalogs."""

import pytest

from astrbot.core.command import (
    CommandEngine,
    CommandResolutionKind,
    build_command_catalog,
)
from astrbot.core.message.components import Plain
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.command_management import (
    list_commands,
    rename_command,
    takeover_command,
)
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata
from tests.unit.test_waking_check_stage import FakeEvent, install_handlers, make_stage


def _command_handler(module_path: str, name: str, plugin: str) -> StarHandlerMetadata:
    async def handler(self, event) -> None: ...

    metadata = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        f"{module_path}_{name}",
        name,
        module_path,
        handler,
        [],
    )
    command_filter = CommandFilter(name)
    command_filter.init_handler_md(metadata)
    metadata.event_filters.append(command_filter)
    metadata.plugin_name = plugin  # type: ignore[attr-defined]
    return metadata


def _group_with_child(
    module_path: str,
    group_name: str,
    child_name: str,
    *,
    alias: set[str] | None = None,
) -> tuple[StarHandlerMetadata, StarHandlerMetadata]:
    group = CommandGroupFilter(group_name, alias=alias)

    def group_handler(self) -> None: ...

    group_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        f"{module_path}_{group_name}_group",
        group_name,
        module_path,
        group_handler,
        [group],
    )

    async def child(self, event) -> None: ...

    child_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        f"{module_path}_{child_name}",
        child_name,
        module_path,
        child,
        [],
        extras_configs={"sub_command": True},
    )
    child_filter = CommandFilter(child_name, parent_command_names=[group_name])
    child_filter.init_handler_md(child_md)
    child_md.event_filters.append(child_filter)
    group.add_sub_command_filter(child_filter)
    return group_md, child_md


def test_same_public_name_is_excluded_from_catalog():
    first = _command_handler("plugin.alpha", "hello", "alpha")
    second = _command_handler("plugin.beta", "hello", "beta")

    catalog = build_command_catalog([first, second])

    assert catalog.resolve("hello").kind is CommandResolutionKind.UNKNOWN_ROOT
    assert ("hello",) not in catalog.commands


@pytest.mark.asyncio
async def test_command_listing_can_be_scoped_to_enabled_plugins(temp_db):
    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(name="alpha", module_path="plugin.alpha", activated=True)
    )
    catalogs.plugins.publish(
        StarMetadata(name="beta", module_path="plugin.beta", activated=True)
    )
    first = _command_handler("plugin.alpha", "hello", "alpha")
    second = _command_handler("plugin.beta", "world", "beta")
    catalogs.handlers.append(first)
    catalogs.handlers.append(second)
    await temp_db.initialize()

    commands = await list_commands(temp_db, catalogs.handlers, {"alpha"})
    assert [item["plugin"] for item in commands] == ["alpha"]


def test_unique_owner_returns_after_rename():
    first = _command_handler("plugin.alpha", "hello", "alpha")
    second = _command_handler("plugin.beta", "hello", "beta")
    second.event_filters[0].command_name = "hi"

    catalog = build_command_catalog([first, second])
    matched = catalog.resolve("hello")

    assert matched.kind is CommandResolutionKind.MATCHED
    assert matched.entries[0].handler_id == first.handler_full_name
    assert catalog.resolve("hi").kind is CommandResolutionKind.MATCHED


def test_conflicting_root_group_suppresses_aliases_and_descendants():
    group_a, child_a = _group_with_child("plugin.alpha", "admin", "run", alias={"adm"})
    group_b, child_b = _group_with_child("plugin.beta", "admin", "list")

    catalog = build_command_catalog([group_a, child_a, group_b, child_b])
    engine = CommandEngine(catalog)

    assert catalog.resolve("admin").kind is CommandResolutionKind.UNKNOWN_ROOT
    assert catalog.resolve("adm").kind is CommandResolutionKind.UNKNOWN_ROOT
    assert catalog.resolve("admin run").kind is CommandResolutionKind.UNKNOWN_ROOT
    assert catalog.resolve("admin list").kind is CommandResolutionKind.UNKNOWN_ROOT
    assert (
        engine.resolve("admin run").resolution.kind
        is CommandResolutionKind.UNKNOWN_ROOT
    )


def test_takeover_winner_keeps_path():
    first = _command_handler("plugin.alpha", "hello", "alpha")
    second = _command_handler("plugin.beta", "hello", "beta")

    catalog = build_command_catalog(
        [first, second],
        path_winners={("hello",): first.handler_full_name},
    )

    matched = catalog.resolve("hello")
    assert matched.kind is CommandResolutionKind.MATCHED
    assert matched.entries[0].handler_id == first.handler_full_name
    assert len(matched.entries) == 1


def test_takeover_root_keeps_winner_descendants_only():
    group_a, child_a = _group_with_child("plugin.alpha", "admin", "run")
    group_b, child_b = _group_with_child("plugin.beta", "admin", "list")

    catalog = build_command_catalog(
        [group_a, child_a, group_b, child_b],
        path_winners={("admin",): group_a.handler_full_name},
    )

    assert catalog.resolve("admin run").kind is CommandResolutionKind.MATCHED
    assert (
        catalog.resolve("admin list").kind is CommandResolutionKind.UNKNOWN_SUBCOMMAND
    )


@pytest.mark.asyncio
async def test_waking_check_does_not_dispatch_conflicted_names(monkeypatch):
    stage = await make_stage()
    first = _command_handler("plugin.alpha", "hello", "alpha")
    second = _command_handler("plugin.beta", "hello", "beta")
    stage.ctx.plugins.publish(
        StarMetadata(name="alpha", module_path="plugin.alpha", activated=True)
    )
    stage.ctx.plugins.publish(
        StarMetadata(name="beta", module_path="plugin.beta", activated=True)
    )
    install_handlers(stage, monkeypatch, [first, second])

    event = FakeEvent([Plain("/hello")], message_text="/hello")
    await stage.process(event)

    assert event.get_extra("activated_handlers", []) == []


@pytest.mark.asyncio
async def test_waking_check_root_group_conflict_has_no_dispatchable_child(
    monkeypatch,
):
    stage = await make_stage()
    group_a, child_a = _group_with_child("plugin.alpha", "admin", "run")
    group_b, child_b = _group_with_child("plugin.beta", "admin", "list")
    stage.ctx.plugins.publish(
        StarMetadata(name="alpha", module_path="plugin.alpha", activated=True)
    )
    stage.ctx.plugins.publish(
        StarMetadata(name="beta", module_path="plugin.beta", activated=True)
    )
    install_handlers(stage, monkeypatch, [group_a, child_a, group_b, child_b])

    event = FakeEvent([Plain("/admin run")], message_text="/admin run")
    await stage.process(event)

    assert event.get_extra("activated_handlers", []) == []
    assert event.stopped is False


@pytest.mark.asyncio
async def test_takeover_command_records_scoped_winner(temp_db):
    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(name="alpha", module_path="plugin.alpha", activated=True)
    )
    catalogs.plugins.publish(
        StarMetadata(name="beta", module_path="plugin.beta", activated=True)
    )
    first = _command_handler("plugin.alpha", "hello", "alpha")
    second = _command_handler("plugin.beta", "hello", "beta")
    catalogs.handlers.append(first)
    catalogs.handlers.append(second)
    await temp_db.initialize()

    descriptor = await takeover_command(
        temp_db,
        catalogs.handlers,
        "alpha:hello",
        config_id="profile-a",
    )
    rows = await temp_db.list_command_conflicts(config_id="profile-a")

    assert descriptor.command_id == "alpha:hello"
    statuses = {row.command_id: row.status for row in rows}
    assert statuses["alpha:hello"] == "takeover"
    assert statuses["beta:hello"] == "pending"
    other = await temp_db.list_command_conflicts(config_id="profile-b")
    assert other == []


@pytest.mark.asyncio
async def test_manual_rename_restores_unique_owner(temp_db, monkeypatch):
    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(name="alpha", module_path="plugin.alpha", activated=True)
    )
    catalogs.plugins.publish(
        StarMetadata(name="beta", module_path="plugin.beta", activated=True)
    )
    first = _command_handler("plugin.alpha", "hello", "alpha")
    second = _command_handler("plugin.beta", "hello", "beta")
    catalogs.handlers.append(first)
    catalogs.handlers.append(second)
    await temp_db.initialize()
    await temp_db.upsert_command_config(
        handler_full_name=first.handler_full_name,
        plugin_name="alpha",
        module_path="plugin.alpha",
        original_command="hello",
        command_id="alpha:hello",
    )
    await temp_db.upsert_command_config(
        handler_full_name=second.handler_full_name,
        plugin_name="beta",
        module_path="plugin.beta",
        original_command="hello",
        command_id="beta:hello",
    )

    await rename_command(temp_db, catalogs.handlers, "beta:hello", "hi")

    assert second.event_filters[0].command_name == "hi"
    catalog = build_command_catalog([first, second])
    assert catalog.resolve("hello").kind is CommandResolutionKind.MATCHED
    assert catalog.resolve("hi").kind is CommandResolutionKind.MATCHED


@pytest.mark.asyncio
async def test_rename_rejects_llm_prefix_root_conflict(temp_db):
    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(name="alpha", module_path="plugin.alpha", activated=True)
    )
    handler = _command_handler("plugin.alpha", "hello", "alpha")
    catalogs.handlers.append(handler)
    await temp_db.initialize()

    with pytest.raises(ValueError, match="LLM"):
        await rename_command(
            temp_db,
            catalogs.handlers,
            "alpha:hello",
            "chat",
            config={
                "command_prefixes": ["/"],
                "llm_access": {"prefixes": ["/chat"]},
            },
        )
