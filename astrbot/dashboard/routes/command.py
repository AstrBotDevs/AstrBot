from quart import request

from astrbot.core.star.command_management import (
    list_command_conflicts,
    list_commands,
)
from astrbot.core.star.command_management import (
    rename_command as rename_command_service,
)
from astrbot.core.star.command_management import (
    toggle_command as toggle_command_service,
)

from .route import Response, Route, RouteContext


class CommandRoute(Route):
    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.routes = {
            "/commands": ("GET", self.get_commands),
            "/commands/conflicts": ("GET", self.get_conflicts),
            "/commands/toggle": ("POST", self.toggle_command),
            "/commands/rename": ("POST", self.rename_command),
            "/commands/permission": ("POST", self.update_permission),
        }
        self.register_routes()

    async def get_commands(self):
        commands = await list_commands()
        summary = {
            "total": len(commands),
            "disabled": len([cmd for cmd in commands if not cmd["enabled"]]),
            "conflicts": len([cmd for cmd in commands if cmd.get("has_conflict")]),
        }
        return Response().ok({"items": commands, "summary": summary}).__dict__

    async def get_conflicts(self):
        conflicts = await list_command_conflicts()
        return Response().ok(conflicts).__dict__

    async def toggle_command(self):
        data = await request.get_json()
        handler_full_name = data.get("handler_full_name")
        enabled = data.get("enabled")

        if handler_full_name is None or enabled is None:
            return Response().error("handler_full_name 与 enabled 均为必填。").__dict__

        if isinstance(enabled, str):
            enabled = enabled.lower() in ("1", "true", "yes", "on")

        try:
            await toggle_command_service(handler_full_name, bool(enabled))
        except ValueError as exc:
            return Response().error(str(exc)).__dict__

        payload = await _get_command_payload(handler_full_name)
        return Response().ok(payload).__dict__

    async def rename_command(self):
        data = await request.get_json()
        handler_full_name = data.get("handler_full_name")
        new_name = data.get("new_name")
        aliases = data.get("aliases")

        if not handler_full_name or not new_name:
            return Response().error("handler_full_name 与 new_name 均为必填。").__dict__

        try:
            await rename_command_service(handler_full_name, new_name, aliases=aliases)
        except ValueError as exc:
            return Response().error(str(exc)).__dict__

        payload = await _get_command_payload(handler_full_name)
        return Response().ok(payload).__dict__

    async def update_permission(self):
        from astrbot.api import sp
        from astrbot.core.star.star_handler import star_handlers_registry
        from astrbot.core.star.star import star_map
        from astrbot.core.star.filter.permission import (
            PermissionTypeFilter,
            PermissionType,
        )

        data = await request.get_json()
        handler_full_name = data.get("handler_full_name")
        permission = data.get("permission")  # "admin" or "member"

        if not handler_full_name or not permission:
            return (
                Response().error("handler_full_name 与 permission 均为必填。").__dict__
            )

        if permission not in ["admin", "member"]:
            return Response().error("permission 必须为 admin 或 member。").__dict__

        handler = star_handlers_registry.get_handler_by_full_name(handler_full_name)
        if not handler:
            return Response().error("未找到该指令").__dict__

        found_plugin = star_map.get(handler.handler_module_path)
        if not found_plugin:
            return Response().error("未找到指令所属插件").__dict__

        # 1. Update Persistent Config (alter_cmd)
        alter_cmd_cfg = await sp.global_get("alter_cmd", {})
        plugin_ = alter_cmd_cfg.get(found_plugin.name, {})
        cfg = plugin_.get(handler.handler_name, {})
        cfg["permission"] = permission
        plugin_[handler.handler_name] = cfg
        alter_cmd_cfg[found_plugin.name] = plugin_

        await sp.global_put("alter_cmd", alter_cmd_cfg)

        # 2. Update Runtime Filter
        found_permission_filter = False
        target_perm_type = (
            PermissionType.ADMIN if permission == "admin" else PermissionType.MEMBER
        )

        for filter_ in handler.event_filters:
            if isinstance(filter_, PermissionTypeFilter):
                filter_.permission_type = target_perm_type
                found_permission_filter = True
                break

        if not found_permission_filter:
            handler.event_filters.insert(0, PermissionTypeFilter(target_perm_type))

        payload = await _get_command_payload(handler_full_name)
        return Response().ok(payload).__dict__


async def _get_command_payload(handler_full_name: str):
    commands = await list_commands()
    for cmd in commands:
        if cmd["handler_full_name"] == handler_full_name:
            return cmd
    return {}
