from types import SimpleNamespace
from typing import Annotated
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event.filter import option
from astrbot.core.command import CommandResolutionKind, build_command_catalog
from astrbot.core.db.po import CommandConfig
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.command_management import (
    list_commands,
    sync_command_configs,
    toggle_command,
    update_command_permission,
)
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import ActionPermissionFilter
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
                "command_id": "demo:tools",
                "handler_full_name": "plugin.demo_tools",
                "sub_commands": [
                    {
                        "command_id": "demo:tools.greet",
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
    payload = await service._get_command_payload("demo:tools.greet")

    assert payload == {
        "command_id": "demo:tools.greet",
        "handler_full_name": "plugin.demo_greet",
        "sub_commands": [],
    }


@pytest.mark.asyncio
async def test_bulk_toggle_builtin_commands_only_updates_builtin_handlers(monkeypatch):
    commands = [
        {
            "command_id": "builtin_commands:help",
            "handler_full_name": "builtin.help",
            "module_path": "astrbot.builtin_stars.builtin_commands.main",
            "sub_commands": [],
        },
        {
            "command_id": "demo:command",
            "handler_full_name": "plugin.command",
            "module_path": "plugin.demo",
            "sub_commands": [
                {
                    "command_id": "builtin_commands:nested",
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

    async def fake_toggle_command(_db, _handlers, command_id, enabled):
        toggled.append((command_id, enabled))

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

    assert toggled == [
        ("builtin_commands:help", False),
        ("builtin_commands:nested", False),
    ]
    assert result == {
        "enabled": False,
        "updated": ["builtin_commands:help", "builtin_commands:nested"],
    }
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


def _publish_builtin_plugin_commands(catalogs: RuntimeCatalogs):
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
        f"{module_path}_plugin_list",
        "plugin_list",
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
        f"{module_path}_plugin_show",
        "plugin_show",
        module_path,
        show_handler,
        [],
        extras_configs={"sub_command": True},
    )
    show_filter.init_handler_md(show_md)
    show_md.event_filters.append(show_filter)
    group.add_sub_command_filter(show_filter)
    catalogs.handlers.append(show_md)
    return module_path, list_filter, list_md, show_filter, show_md


@pytest.mark.asyncio
async def test_sync_keeps_declared_builtin_names_and_manual_renames():
    catalogs = RuntimeCatalogs()
    module_path, list_filter, list_md, show_filter, show_md = (
        _publish_builtin_plugin_commands(catalogs)
    )

    configs = [
        CommandConfig(
            handler_full_name=list_md.handler_full_name,
            command_id="builtin_commands:plugin.list",
            plugin_name="builtin_commands",
            module_path=module_path,
            original_command="plugin ls",
            resolved_command="ls",
            enabled=False,
        ),
        CommandConfig(
            handler_full_name=show_md.handler_full_name,
            command_id="builtin_commands:plugin.show",
            plugin_name="builtin_commands",
            module_path=module_path,
            original_command="plugin show",
            resolved_command="inspect",
            enabled=True,
            resolution_strategy="manual_rename",
        ),
    ]
    upserts: list[dict] = []
    deleted: list[str] = []

    async def upsert_command_config(**kwargs):
        upserts.append(kwargs)
        data = {
            key: value
            for key, value in kwargs.items()
            if key != "previous_handler_full_name"
        }
        return CommandConfig(**data)

    db = SimpleNamespace(
        get_command_configs=AsyncMock(return_value=configs),
        upsert_command_config=upsert_command_config,
        delete_command_configs=AsyncMock(
            side_effect=lambda names: deleted.extend(names)
        ),
    )

    await sync_command_configs(db, catalogs.handlers)

    assert upserts == []
    assert list_filter.command_name == "list"
    assert list_md.enabled is False
    assert show_filter.command_name == "inspect"
    assert deleted == []


@pytest.mark.asyncio
async def test_sync_relinks_by_command_id_and_drops_unmatched_fossils():
    catalogs = RuntimeCatalogs()
    module_path, list_filter, list_md, _, _ = _publish_builtin_plugin_commands(catalogs)

    configs = [
        CommandConfig(
            handler_full_name=f"{module_path}_plugin_ls",
            command_id="builtin_commands:plugin.list",
            plugin_name="builtin_commands",
            module_path=module_path,
            original_command="plugin list",
            resolved_command="ls",
            enabled=False,
            extra_data={"resolved_aliases": ["plist"]},
        ),
        CommandConfig(
            handler_full_name=f"{module_path}_plugin_help",
            command_id="builtin_commands:plugin.help",
            plugin_name="builtin_commands",
            module_path=module_path,
            original_command="plugin help",
            resolved_command="help",
            enabled=False,
        ),
    ]
    upserts: list[dict] = []
    deleted: list[str] = []

    async def upsert_command_config(**kwargs):
        upserts.append(kwargs)
        data = {
            key: value
            for key, value in kwargs.items()
            if key != "previous_handler_full_name"
        }
        return CommandConfig(**data)

    async def get_command_config(handler_full_name: str):
        return None

    db = SimpleNamespace(
        get_command_configs=AsyncMock(return_value=configs),
        get_command_config=get_command_config,
        upsert_command_config=upsert_command_config,
        delete_command_config=AsyncMock(),
        delete_command_configs=AsyncMock(
            side_effect=lambda names: deleted.extend(names)
        ),
    )

    await sync_command_configs(db, catalogs.handlers)

    assert len(upserts) == 1
    assert upserts[0]["handler_full_name"] == list_md.handler_full_name
    assert upserts[0]["previous_handler_full_name"] == f"{module_path}_plugin_ls"
    assert upserts[0]["command_id"] == "builtin_commands:plugin.list"
    assert upserts[0]["enabled"] is False
    assert list_filter.command_name == "list"
    assert list_filter.alias == set()
    assert deleted == [f"{module_path}_plugin_help"]


@pytest.mark.asyncio
async def test_sync_drops_unmatched_legacy_command_ids():
    catalogs = RuntimeCatalogs()
    module_path, list_filter, list_md, _, _ = _publish_builtin_plugin_commands(catalogs)
    fossil_name = f"{module_path}_plugin_ls"
    deleted: list[str] = []

    db = SimpleNamespace(
        get_command_configs=AsyncMock(
            return_value=[
                CommandConfig(
                    handler_full_name=fossil_name,
                    command_id="builtin_commands:plugin.ls",
                    plugin_name="builtin_commands",
                    module_path=module_path,
                    original_command="plugin ls",
                    resolved_command="ls",
                    enabled=False,
                    extra_data={"resolved_aliases": ["plist"]},
                )
            ]
        ),
        upsert_command_config=AsyncMock(),
        delete_command_configs=AsyncMock(
            side_effect=lambda names: deleted.extend(names)
        ),
    )

    await sync_command_configs(db, catalogs.handlers)

    assert deleted == [fossil_name]
    assert list_filter.command_name == "list"
    assert list_md.enabled is True
    assert list_filter.alias == set()


@pytest.mark.asyncio
async def test_toggle_command_preserves_manual_rename_only():
    catalogs = RuntimeCatalogs()
    module_path, list_filter, list_md, show_filter, show_md = (
        _publish_builtin_plugin_commands(catalogs)
    )
    stored = {
        list_md.handler_full_name: CommandConfig(
            handler_full_name=list_md.handler_full_name,
            command_id="builtin_commands:plugin.list",
            plugin_name="builtin_commands",
            module_path=module_path,
            original_command="plugin list",
            resolved_command="ls",
            enabled=True,
        ),
        show_md.handler_full_name: CommandConfig(
            handler_full_name=show_md.handler_full_name,
            command_id="builtin_commands:plugin.show",
            plugin_name="builtin_commands",
            module_path=module_path,
            original_command="plugin show",
            resolved_command="inspect",
            enabled=True,
            resolution_strategy="manual_rename",
        ),
    }
    upserts: list[dict] = []

    async def get_command_config(handler_full_name: str):
        return stored.get(handler_full_name)

    async def get_command_config_by_command_id(command_id: str):
        return next(
            (row for row in stored.values() if row.command_id == command_id),
            None,
        )

    async def upsert_command_config(**kwargs):
        upserts.append(kwargs)
        data = {
            key: value
            for key, value in kwargs.items()
            if key != "previous_handler_full_name"
        }
        config = CommandConfig(**data)
        stored[config.handler_full_name] = config
        return config

    async def get_command_configs():
        return list(stored.values())

    db = SimpleNamespace(
        get_command_config=get_command_config,
        get_command_config_by_command_id=get_command_config_by_command_id,
        upsert_command_config=upsert_command_config,
        get_command_configs=get_command_configs,
        delete_command_configs=AsyncMock(),
    )

    await toggle_command(db, catalogs.handlers, "builtin_commands:plugin.list", False)
    list_upsert = next(
        row for row in upserts if row["command_id"] == "builtin_commands:plugin.list"
    )
    assert list_upsert["resolved_command"] == "list"
    assert list_upsert["enabled"] is False
    assert list_filter.command_name == "list"

    upserts.clear()
    await toggle_command(db, catalogs.handlers, "builtin_commands:plugin.show", False)
    show_upsert = next(
        row for row in upserts if row["command_id"] == "builtin_commands:plugin.show"
    )
    assert show_upsert["resolved_command"] == "inspect"
    assert show_upsert["enabled"] is False
    assert show_filter.command_name == "inspect"


@pytest.mark.asyncio
async def test_update_command_permission_writes_command_id_without_migrating_fossils():
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

    async def list_handler(self, event) -> None: ...

    list_filter = CommandFilter("list", parent_command_names=["plugin"])
    list_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        f"{module_path}_plugin_list",
        "plugin_list",
        module_path,
        list_handler,
        [ActionPermissionFilter("extension.read")],
        extras_configs={"sub_command": True},
    )
    list_filter.init_handler_md(list_md)
    list_md.event_filters.append(list_filter)
    catalogs.handlers.append(list_md)

    stored = {
        "builtin_commands": {
            "plugin_ls": {"permission_action": "extension.read"},
        }
    }

    async def global_get(key, default=None):
        assert key == "alter_cmd"
        return stored

    writes: list[dict] = []

    async def global_put(key, value):
        assert key == "alter_cmd"
        writes.append(value)

    preferences = SimpleNamespace(global_get=global_get, global_put=global_put)

    descriptor = await update_command_permission(
        preferences,
        catalogs.handlers,
        "builtin_commands:plugin.list",
        "extension.manage",
    )

    assert descriptor.command_id == "builtin_commands:plugin.list"
    assert writes[0]["builtin_commands"] == {
        "plugin_ls": {"permission_action": "extension.read"},
        "builtin_commands:plugin.list": {"permission_action": "extension.manage"},
    }
    permission = next(
        filter_
        for filter_ in list_md.event_filters
        if isinstance(filter_, ActionPermissionFilter)
    )
    assert permission.action == "extension.manage"


def _append_named_command(
    catalogs: RuntimeCatalogs, *, module_path: str, command_name: str
) -> None:
    async def handler(self, event) -> None: ...

    handler.__module__ = module_path
    metadata = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        f"{module_path}_{command_name}",
        command_name,
        module_path,
        handler,
        [],
    )
    metadata.event_filters.append(CommandFilter(command_name))
    catalogs.handlers.append(metadata)


@pytest.mark.asyncio
async def test_list_commands_serializes_plugin_activation_without_mutating_enabled():
    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(
            name="foo",
            module_path="data.plugins.foo.main",
            activated=True,
        )
    )
    catalogs.plugins.publish(
        StarMetadata(
            name="bar",
            module_path="data.plugins.bar.main",
            activated=False,
        )
    )
    _append_named_command(
        catalogs, module_path="data.plugins.foo.main", command_name="alpha"
    )
    _append_named_command(
        catalogs, module_path="data.plugins.bar.main", command_name="beta"
    )
    _append_named_command(
        catalogs, module_path="data.plugins.missing.main", command_name="gamma"
    )

    commands = await list_commands(
        SimpleNamespace(get_command_configs=AsyncMock(return_value=[])),
        catalogs.handlers,
    )
    by_plugin = {item["plugin"]: item for item in commands}

    assert by_plugin["foo"]["enabled"] is True
    assert by_plugin["foo"]["plugin_activated"] is True
    assert by_plugin["bar"]["enabled"] is True
    assert by_plugin["bar"]["plugin_activated"] is False
    assert by_plugin["data.plugins.missing.main"]["plugin_activated"] is True


@pytest.mark.asyncio
async def test_inactive_plugin_commands_are_excluded_from_conflicts():
    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(
            name="foo",
            module_path="data.plugins.foo.main",
            activated=True,
        )
    )
    catalogs.plugins.publish(
        StarMetadata(
            name="bar",
            module_path="data.plugins.bar.main",
            activated=False,
        )
    )
    _append_named_command(
        catalogs, module_path="data.plugins.foo.main", command_name="demo"
    )
    _append_named_command(
        catalogs, module_path="data.plugins.bar.main", command_name="demo"
    )

    commands = await list_commands(
        SimpleNamespace(get_command_configs=AsyncMock(return_value=[])),
        catalogs.handlers,
    )

    assert all(item["has_conflict"] is False for item in commands)
