from quart import request

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
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
from astrbot.core.star.command_management import (
    update_command_permission as update_command_permission_service,
)

from .route import Response, Route, RouteContext


class CommandRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.routes = {
            "/commands": ("GET", self.get_commands),
            "/commands/conflicts": ("GET", self.get_conflicts),
            "/commands/toggle": ("POST", self.toggle_command),
            "/commands/rename": ("POST", self.rename_command),
            "/commands/permission": ("POST", self.update_permission),
        }
        self.register_routes()

    async def get_commands(self):
        commands = await _list_dashboard_commands(self.core_lifecycle)
        summary = {
            "total": len(commands),
            "disabled": len([cmd for cmd in commands if not cmd["enabled"]]),
            "conflicts": len([cmd for cmd in commands if cmd.get("has_conflict")]),
        }
        return Response().ok({"items": commands, "summary": summary}).__dict__

    async def get_conflicts(self):
        conflicts = await _list_dashboard_conflicts(self.core_lifecycle)
        return Response().ok(conflicts).__dict__

    async def toggle_command(self):
        data = await request.get_json()
        command_key = _resolve_command_key(data)
        enabled = data.get("enabled")

        if command_key is None or enabled is None:
            return Response().error("command_key 与 enabled 均为必填。").__dict__

        if isinstance(enabled, str):
            enabled = enabled.lower() in ("1", "true", "yes", "on")

        item = await _get_command_payload(self.core_lifecycle, command_key)
        if item.get("runtime_kind") == "sdk":
            return (
                Response()
                .error("SDK commands are read-only in the dashboard.")
                .__dict__
            )

        try:
            await toggle_command_service(command_key, bool(enabled))
        except ValueError as exc:
            return Response().error(str(exc)).__dict__

        payload = await _get_command_payload(self.core_lifecycle, command_key)
        return Response().ok(payload).__dict__

    async def rename_command(self):
        data = await request.get_json()
        command_key = _resolve_command_key(data)
        new_name = data.get("new_name")
        aliases = data.get("aliases")

        if not command_key or not new_name:
            return Response().error("command_key 与 new_name 均为必填。").__dict__

        item = await _get_command_payload(self.core_lifecycle, command_key)
        if item.get("runtime_kind") == "sdk":
            return (
                Response()
                .error("SDK commands are read-only in the dashboard.")
                .__dict__
            )

        try:
            await rename_command_service(command_key, new_name, aliases=aliases)
        except ValueError as exc:
            return Response().error(str(exc)).__dict__

        payload = await _get_command_payload(self.core_lifecycle, command_key)
        return Response().ok(payload).__dict__

    async def update_permission(self):
        data = await request.get_json()
        command_key = _resolve_command_key(data)
        permission = data.get("permission")

        if not command_key or not permission:
            return Response().error("command_key 与 permission 均为必填。").__dict__

        item = await _get_command_payload(self.core_lifecycle, command_key)
        if item.get("runtime_kind") == "sdk":
            return (
                Response()
                .error("SDK commands are read-only in the dashboard.")
                .__dict__
            )

        try:
            await update_command_permission_service(command_key, permission)
        except ValueError as exc:
            return Response().error(str(exc)).__dict__

        payload = await _get_command_payload(self.core_lifecycle, command_key)
        return Response().ok(payload).__dict__


def _resolve_command_key(data: dict | None) -> str | None:
    if not isinstance(data, dict):
        return None
    command_key = data.get("command_key")
    if command_key:
        return str(command_key)
    handler_full_name = data.get("handler_full_name")
    if handler_full_name:
        return str(handler_full_name)
    return None


async def _list_dashboard_commands(
    core_lifecycle: AstrBotCoreLifecycle,
) -> list[dict]:
    commands = _decorate_legacy_commands(await list_commands())
    sdk_bridge = getattr(core_lifecycle, "sdk_plugin_bridge", None)
    if sdk_bridge is not None:
        commands.extend(sdk_bridge.list_dashboard_commands())
    _apply_conflict_flags(commands)
    commands.sort(key=lambda item: str(item.get("effective_command", "")).lower())
    return commands


async def _list_dashboard_conflicts(
    core_lifecycle: AstrBotCoreLifecycle,
) -> list[dict]:
    conflicts = list(await list_command_conflicts())
    sdk_bridge = getattr(core_lifecycle, "sdk_plugin_bridge", None)
    if sdk_bridge is None or not hasattr(
        sdk_bridge, "list_cross_system_command_conflicts"
    ):
        return conflicts
    conflicts.extend(
        conflict.to_dashboard_payload()
        for conflict in sdk_bridge.list_cross_system_command_conflicts()
    )
    return conflicts


def _decorate_legacy_commands(commands: list[dict]) -> list[dict]:
    for item in commands:
        _decorate_legacy_command_item(item)
    return commands


def _decorate_legacy_command_item(item: dict) -> None:
    item["command_key"] = str(item.get("handler_full_name", ""))
    item["runtime_kind"] = "legacy"
    item["supports_toggle"] = True
    item["supports_rename"] = True
    item["supports_permission"] = True
    sub_commands = item.get("sub_commands")
    if not isinstance(sub_commands, list):
        return
    for sub in sub_commands:
        if isinstance(sub, dict):
            _decorate_legacy_command_item(sub)


def _apply_conflict_flags(commands: list[dict]) -> None:
    counts: dict[str, int] = {}
    for item in _walk_command_items(commands):
        command_name = str(item.get("effective_command", "")).strip()
        if not command_name or not bool(item.get("enabled", False)):
            continue
        counts[command_name] = counts.get(command_name, 0) + 1

    for item in _walk_command_items(commands):
        command_name = str(item.get("effective_command", "")).strip()
        item["has_conflict"] = bool(command_name and counts.get(command_name, 0) > 1)


def _walk_command_items(commands: list[dict]):
    for item in commands:
        yield item
        sub_commands = item.get("sub_commands")
        if not isinstance(sub_commands, list):
            continue
        yield from _walk_command_items(sub_commands)


async def _get_command_payload(
    core_lifecycle: AstrBotCoreLifecycle,
    command_key: str,
):
    commands = await _list_dashboard_commands(core_lifecycle)
    for cmd in _walk_command_items(commands):
        if cmd.get("command_key") == command_key:
            return cmd
    return {}
