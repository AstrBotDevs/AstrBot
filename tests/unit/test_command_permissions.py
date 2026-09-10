from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.star import command_management as management
from astrbot.core.star import star_manager
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.permission import (
    COMMAND_PERMISSION_TYPES,
    PermissionType,
    PermissionTypeFilter,
)
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    StarHandlerRegistry,
)


@pytest.mark.parametrize("permission", COMMAND_PERMISSION_TYPES)
@pytest.mark.parametrize("group", [False, True])
@pytest.mark.parametrize("admin", [False, True])
def test_permission_matrix(permission, group, admin):
    event = MagicMock()
    event.get_group_id.return_value = "group" if group else ""
    event.is_admin.return_value = admin
    expected = (
        admin or permission == "member" or (permission == "group_admin" and not group)
    )
    assert (
        PermissionTypeFilter(COMMAND_PERMISSION_TYPES[permission]).filter(event, {})
        == expected
    )


@pytest.fixture
def command(monkeypatch):
    async def probe(self, event):
        pass

    module = "data.plugins.permission_probe.main"
    handler = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"{module}_probe",
        handler_name="probe",
        handler_module_path=module,
        handler=probe,
        event_filters=[PermissionTypeFilter(PermissionType.GROUP_ADMIN)],
    )
    handler.event_filters.append(CommandFilter("probe", handler_md=handler))
    registry = StarHandlerRegistry()
    registry.append(handler)
    metadata = StarMetadata(name="permission_probe", module_path=module)
    for target in (management, star_manager):
        monkeypatch.setattr(target, "star_handlers_registry", registry)
        monkeypatch.setattr(target, "star_map", {module: metadata})
    saved = {}
    monkeypatch.setattr(
        management.sp,
        "global_get",
        AsyncMock(side_effect=lambda key, default=None: saved.get(key, default)),
    )
    monkeypatch.setattr(
        management.sp,
        "global_put",
        AsyncMock(side_effect=lambda key, value: saved.__setitem__(key, value)),
    )
    return handler, metadata, saved


@pytest.mark.asyncio
@pytest.mark.parametrize("permission", COMMAND_PERMISSION_TYPES)
@pytest.mark.parametrize("existing_filter", [False, True])
async def test_update_permission_persists_and_serializes(
    command, permission, existing_filter
):
    handler, _, saved = command
    if not existing_filter:
        handler.event_filters.pop(0)
    descriptor = await management.update_command_permission(
        handler.handler_full_name, permission
    )
    assert descriptor.permission == permission
    assert saved["alter_cmd"]["permission_probe"]["probe"]["permission"] == permission
    filters = [f for f in handler.event_filters if isinstance(f, PermissionTypeFilter)]
    assert len(filters) == 1
    assert filters[0].permission_type == COMMAND_PERMISSION_TYPES[permission]
    assert descriptor.effective_command == "probe"


@pytest.mark.asyncio
@pytest.mark.parametrize("permission", ["everyone", "invalid", ""])
async def test_invalid_permission_does_not_change_state(command, permission):
    handler, _, saved = command
    with pytest.raises(ValueError, match="Permission must"):
        await management.update_command_permission(
            handler.handler_full_name, permission
        )
    assert saved == {}
    assert management._determine_permission(handler) == "group_admin"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        {},
        {"alias": "renamed"},
        {"permission": "invalid"},
        {"permission": "member"},
        {"permission": "admin"},
        {"permission": "group_admin"},
    ],
)
@pytest.mark.parametrize("existing_filter", [False, True])
async def test_plugin_load_restores_only_explicit_permission(
    command, monkeypatch, tmp_path, config, existing_filter
):
    handler, metadata, saved = command
    if not existing_filter:
        handler.event_filters.pop(0)
    saved["alter_cmd"] = {"permission_probe": {"probe": config}}
    manager = star_manager.PluginManager.__new__(star_manager.PluginManager)
    manager.plugin_store_path = str(tmp_path)
    manager.conf_schema_fname = "_conf_schema.json"
    manager.logo_fname = "logo.png"
    manager.failed_plugin_dict = {}
    monkeypatch.setattr(
        manager,
        "_get_plugin_modules",
        lambda: [{"module": "main", "pname": "permission_probe"}],
    )
    monkeypatch.setattr(
        manager,
        "_import_plugin_with_dependency_recovery",
        AsyncMock(return_value=ModuleType(metadata.module_path)),
    )
    monkeypatch.setattr(manager, "_load_plugin_metadata", lambda **kwargs: None)
    monkeypatch.setattr(manager, "_rebuild_failed_plugin_info", lambda: None)
    monkeypatch.setattr(star_manager, "sync_command_configs", AsyncMock())
    success, error = await manager.load(
        specified_module_path=metadata.module_path, ignore_version_check=True
    )
    assert success, error
    expected = config.get("permission")
    if expected not in COMMAND_PERMISSION_TYPES:
        expected = "group_admin" if existing_filter else "everyone"
    assert management._determine_permission(handler) == expected
    assert metadata.star_handler_full_names == [handler.handler_full_name]
