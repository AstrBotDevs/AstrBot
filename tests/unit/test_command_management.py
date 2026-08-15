from types import SimpleNamespace
from typing import Annotated
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event.filter import option
from astrbot.core.command import CommandResolutionKind, build_command_catalog
from astrbot.core.db.po import CommandConfig
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.command_management import list_commands, sync_command_configs
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata
from astrbot.dashboard.services.command_service import CommandService


@pytest.mark.asyncio
async def test_list_commands_includes_signature_metadata():
    catalogs = RuntimeCatalogs()

    async def fake_get_command_configs():
        return []

    db = SimpleNamespace(get_command_configs=fake_get_command_configs)

    plugin = StarMetadata(
        name="demo",
        module_path="plugin.demo",
        activated=True,
    )
    catalogs.plugins.publish(plugin)

    async def tools(self, event) -> None: ...

    tools.__module__ = "plugin.demo"
    tools_handler = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name="plugin.demo_tools",
        handler_name="tools",
        handler_module_path="plugin.demo",
        handler=tools,
        event_filters=[],
        desc="Tool commands",
    )
    tools_filter = CommandGroupFilter("tools", alias={"t"})
    tools_handler.event_filters.append(tools_filter)
    catalogs.handlers.append(tools_handler)

    async def greet(
        self,
        event,
        name: str,
        force: Annotated[bool, option("--force", "-f")] = False,
    ) -> None: ...

    greet.__module__ = "plugin.demo"
    greet_handler = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name="plugin.demo_greet",
        handler_name="greet",
        handler_module_path="plugin.demo",
        handler=greet,
        event_filters=[],
        desc="Greet someone",
        extras_configs={"sub_command": True},
    )
    greet_filter = CommandFilter(
        "greet",
        alias={"hello"},
        parent_command_names=tools_filter.get_complete_command_names(),
    )
    greet_filter.init_handler_md(greet_handler)
    greet_handler.event_filters.append(greet_filter)
    catalogs.handlers.append(greet_handler)

    commands = await list_commands(db, catalogs.handlers)

    assert len(commands) == 1
    group = commands[0]
    assert group["effective_command"] == "tools"
    assert group["signature"] == "tools"
    assert group["display_signature"] == "tools [aliases: t]"

    assert len(group["sub_commands"]) == 1
    sub_command = group["sub_commands"][0]
    assert sub_command["effective_command"] == "tools greet"
    assert (
        sub_command["signature"]
        == "tools greet (name(str),force[--force/-f](bool)=False)"
    )
    assert (
        sub_command["display_signature"]
        == "tools greet (name(str),force[--force/-f](bool)=False) [aliases: hello]"
    )


@pytest.mark.asyncio
async def test_group_rename_rebuilds_descendant_command_paths():
    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(
            name="demo",
            module_path="plugin.demo",
            activated=True,
        )
    )

    def tools(self) -> None: ...

    tools.__module__ = "plugin.demo"
    tools_handler = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "plugin.demo_tools",
        "tools",
        "plugin.demo",
        tools,
        [],
    )
    tools_filter = CommandGroupFilter("tools")
    tools_handler.event_filters.append(tools_filter)
    catalogs.handlers.append(tools_handler)

    async def run(self, event) -> None: ...

    run.__module__ = "plugin.demo"
    run_handler = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "plugin.demo_run",
        "run",
        "plugin.demo",
        run,
        [],
        extras_configs={"sub_command": True},
    )
    run_filter = CommandFilter("run", parent_command_names=["tools"])
    run_filter.init_handler_md(run_handler)
    run_handler.event_filters.append(run_filter)
    tools_filter.add_sub_command_filter(run_filter)
    catalogs.handlers.append(run_handler)

    configs = [
        CommandConfig(
            handler_full_name=tools_handler.handler_full_name,
            plugin_name="demo",
            module_path="plugin.demo",
            original_command="tools",
            resolved_command="renamed",
            enabled=True,
            resolution_strategy="manual_rename",
        )
    ]
    db = SimpleNamespace(get_command_configs=AsyncMock(return_value=configs))

    commands = await list_commands(db, catalogs.handlers)

    assert len(commands) == 1
    assert commands[0]["effective_command"] == "renamed"
    assert commands[0]["original_command"] == "tools"
    assert len(commands[0]["sub_commands"]) == 1
    child = commands[0]["sub_commands"][0]
    assert child["parent_signature"] == "renamed"
    assert child["effective_command"] == "renamed run"
    assert child["original_command"] == "tools run"
    assert run_filter.get_complete_command_names() == ["renamed run"]


def test_catalog_excludes_subcommands_when_parent_group_is_disabled():
    def group_handler(self) -> None: ...

    group = CommandGroupFilter("admin")
    group_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "plugin.demo_admin",
        "admin",
        "plugin.demo",
        group_handler,
        [group],
        enabled=False,
    )

    async def run(self, event) -> None: ...

    child_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "plugin.demo_admin_run",
        "run",
        "plugin.demo",
        run,
        [],
        extras_configs={"sub_command": True},
    )
    child = CommandFilter("run", parent_command_names=["admin"])
    child.init_handler_md(child_md)
    child_md.event_filters.append(child)
    group.add_sub_command_filter(child)

    catalog = build_command_catalog([child_md])

    assert group_md.enabled is False
    assert catalog.resolve("admin run").kind is CommandResolutionKind.UNKNOWN_ROOT


@pytest.mark.asyncio
async def test_command_service_finds_nested_subcommand_payload(monkeypatch):
    async def fake_list_commands(_db, _handlers):
        return [
            {
                "handler_full_name": "plugin.demo_tools",
                "sub_commands": [
                    {
                        "handler_full_name": "plugin.demo_greet",
                        "sub_commands": [],
                    }
                ],
            }
        ]

    monkeypatch.setattr(
        "astrbot.dashboard.services.command_service.list_commands",
        fake_list_commands,
    )

    service = CommandService(
        {},
        SimpleNamespace(),
        SimpleNamespace(),
        RuntimeCatalogs().handlers,
        SimpleNamespace(refresh_command_catalogs=lambda: None),
        SimpleNamespace(refresh_registered_commands=AsyncMock()),
        SimpleNamespace(confs={}),
    )
    payload = await service._get_command_payload("plugin.demo_greet")

    assert payload == {
        "handler_full_name": "plugin.demo_greet",
        "sub_commands": [],
    }


@pytest.mark.asyncio
async def test_bulk_toggle_builtin_commands_only_updates_builtin_handlers(monkeypatch):
    commands = [
        {
            "handler_full_name": "builtin.help",
            "module_path": "astrbot.builtin_stars.builtin_commands.main",
            "sub_commands": [],
        },
        {
            "handler_full_name": "plugin.command",
            "module_path": "plugin.demo",
            "sub_commands": [
                {
                    "handler_full_name": "builtin.nested",
                    "module_path": "astrbot.builtin_stars.builtin_commands.main",
                    "sub_commands": [],
                }
            ],
        },
    ]
    toggled = []

    async def fake_list_commands(_db, _handlers):
        return commands

    async def fake_toggle_command(_db, _handlers, handler_full_name, enabled):
        toggled.append((handler_full_name, enabled))

    monkeypatch.setattr(
        "astrbot.dashboard.services.command_service.list_commands", fake_list_commands
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.command_service.toggle_command",
        fake_toggle_command,
    )
    refresh_registered_commands = AsyncMock()
    catalog_refreshes = []
    catalogs = RuntimeCatalogs()
    service = CommandService(
        {},
        SimpleNamespace(),
        SimpleNamespace(),
        catalogs.handlers,
        SimpleNamespace(
            refresh_command_catalogs=lambda: catalog_refreshes.append(True),
        ),
        SimpleNamespace(refresh_registered_commands=refresh_registered_commands),
        SimpleNamespace(confs={}),
    )

    result = await service.bulk_toggle_builtin_commands(False)

    assert toggled == [("builtin.help", False), ("builtin.nested", False)]
    assert result == {"enabled": False, "updated": ["builtin.help", "builtin.nested"]}
    assert catalog_refreshes == [True]
    refresh_registered_commands.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_commands_uses_configured_aliases_in_display_signature():
    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(
            name="demo",
            module_path="plugin.demo",
            activated=True,
        )
    )

    async def greet(self, event, name: str) -> None: ...

    greet.__module__ = "plugin.demo"
    greet_handler = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name="plugin.demo_greet",
        handler_name="greet",
        handler_module_path="plugin.demo",
        handler=greet,
        event_filters=[],
        desc="Greet someone",
    )
    greet_filter = CommandFilter("greet", alias={"hello"})
    greet_filter.init_handler_md(greet_handler)
    greet_handler.event_filters.append(greet_filter)
    catalogs.handlers.append(greet_handler)

    async def fake_get_command_configs():
        return [
            CommandConfig(
                handler_full_name="plugin.demo_greet",
                plugin_name="demo",
                module_path="plugin.demo",
                original_command="greet",
                resolved_command="welcome",
                enabled=True,
                extra_data={"resolved_aliases": ["hi", "yo"]},
            )
        ]

    db = SimpleNamespace(get_command_configs=fake_get_command_configs)

    commands = await list_commands(db, catalogs.handlers)

    assert len(commands) == 1
    assert commands[0]["effective_command"] == "welcome"
    assert commands[0]["aliases"] == ["hi", "yo"]
    assert commands[0]["display_signature"] == "welcome (name(str)) [aliases: hi, yo]"


@pytest.mark.asyncio
async def test_sync_migrates_builtin_defaults_and_preserves_manual_renames():
    catalogs = RuntimeCatalogs()
    module_path = "astrbot.builtin_stars.builtin_commands.main"
    catalogs.plugins.publish(
        StarMetadata(
            name="builtin_commands",
            module_path=module_path,
            activated=True,
            reserved=True,
        )
    )

    def group_handler(self) -> None: ...

    group_handler.__module__ = module_path
    group = CommandGroupFilter("plugin")
    group_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        f"{module_path}_plugin",
        "plugin",
        module_path,
        group_handler,
        [group],
    )
    catalogs.handlers.append(group_md)

    async def list_handler(self, event) -> None: ...

    list_filter = CommandFilter("list", parent_command_names=["plugin"])
    list_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        f"{module_path}_plugin_ls",
        "plugin_ls",
        module_path,
        list_handler,
        [],
        extras_configs={"sub_command": True},
    )
    list_filter.init_handler_md(list_md)
    list_md.event_filters.append(list_filter)
    group.add_sub_command_filter(list_filter)
    catalogs.handlers.append(list_md)

    async def show_handler(self, event) -> None: ...

    show_filter = CommandFilter("show", parent_command_names=["plugin"])
    show_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        f"{module_path}_plugin_help",
        "plugin_help",
        module_path,
        show_handler,
        [],
        extras_configs={"sub_command": True},
    )
    show_filter.init_handler_md(show_md)
    show_md.event_filters.append(show_filter)
    group.add_sub_command_filter(show_filter)
    catalogs.handlers.append(show_md)

    configs = [
        CommandConfig(
            handler_full_name=list_md.handler_full_name,
            plugin_name="builtin_commands",
            module_path=module_path,
            original_command="plugin ls",
            resolved_command="ls",
            enabled=False,
        ),
        CommandConfig(
            handler_full_name=show_md.handler_full_name,
            plugin_name="builtin_commands",
            module_path=module_path,
            original_command="plugin help",
            resolved_command="inspect",
            enabled=True,
            resolution_strategy="manual_rename",
        ),
    ]
    upserts: list[dict] = []
    deleted: list[str] = []

    async def upsert_command_config(**kwargs):
        upserts.append(kwargs)
        return CommandConfig(**kwargs)

    db = SimpleNamespace(
        get_command_configs=AsyncMock(return_value=configs),
        upsert_command_config=upsert_command_config,
        delete_command_configs=AsyncMock(
            side_effect=lambda names: deleted.extend(names)
        ),
    )

    await sync_command_configs(db, catalogs.handlers)

    assert len(upserts) == 1
    assert upserts[0]["handler_full_name"] == list_md.handler_full_name
    assert upserts[0]["original_command"] == "plugin list"
    assert upserts[0]["resolved_command"] == "list"
    assert upserts[0]["enabled"] is False
    assert list_filter.command_name == "list"
    assert show_filter.command_name == "inspect"
    assert deleted == []
