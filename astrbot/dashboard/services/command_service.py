from __future__ import annotations

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star.command_management import (
    list_command_conflicts,
    list_commands,
    rename_command,
    toggle_command,
    update_command_permission,
)


class CommandServiceError(Exception):
    pass


class CommandService:
    def __init__(
        self,
        config: AstrBotConfig,
        core_lifecycle: AstrBotCoreLifecycle | None = None,
    ) -> None:
        self.config = config
        self.core_lifecycle = core_lifecycle

    async def list_commands(self, config_id: str = "") -> dict:
        commands = await list_commands()
        summary = {
            "total": len(commands),
            "disabled": len([cmd for cmd in commands if not cmd["enabled"]]),
            "conflicts": len([cmd for cmd in commands if cmd.get("has_conflict")]),
        }
        wake_prefix = self._get_wake_prefix(config_id)
        return {
            "items": commands,
            "summary": summary,
            "wake_prefix": wake_prefix,
        }

    async def list_commands_from_legacy_query(self, config_id: str | None) -> dict:
        return await self.list_commands(config_id or "")

    async def list_conflicts(self):
        return await list_command_conflicts()

    async def toggle_command(self, handler_full_name: str | None, enabled) -> dict:
        if handler_full_name is None or enabled is None:
            raise CommandServiceError("handler_full_name 与 enabled 均为必填。")

        if isinstance(enabled, str):
            enabled = enabled.lower() in ("1", "true", "yes", "on")

        try:
            await toggle_command(handler_full_name, bool(enabled))
        except ValueError as exc:
            raise CommandServiceError(str(exc)) from exc

        return await self._get_command_payload(handler_full_name)

    async def toggle_command_from_legacy_payload(self, data: object) -> dict:
        payload = self._payload(data)
        return await self.toggle_command(
            payload.get("handler_full_name"),
            payload.get("enabled"),
        )

    async def rename_command(
        self,
        handler_full_name: str | None,
        new_name: str | None,
        aliases=None,
    ) -> dict:
        if not handler_full_name or not new_name:
            raise CommandServiceError("handler_full_name 与 new_name 均为必填。")

        try:
            await rename_command(handler_full_name, new_name, aliases=aliases)
        except ValueError as exc:
            raise CommandServiceError(str(exc)) from exc

        return await self._get_command_payload(handler_full_name)

    async def rename_command_from_legacy_payload(self, data: object) -> dict:
        payload = self._payload(data)
        return await self.rename_command(
            payload.get("handler_full_name"),
            payload.get("new_name"),
            aliases=payload.get("aliases"),
        )

    async def update_permission(
        self,
        handler_full_name: str | None,
        permission: str | None,
    ) -> dict:
        if not handler_full_name or not permission:
            raise CommandServiceError("handler_full_name 与 permission 均为必填。")

        try:
            await update_command_permission(handler_full_name, permission)
        except ValueError as exc:
            raise CommandServiceError(str(exc)) from exc

        return await self._get_command_payload(handler_full_name)

    async def update_permission_from_legacy_payload(self, data: object) -> dict:
        payload = self._payload(data)
        return await self.update_permission(
            payload.get("handler_full_name"),
            payload.get("permission"),
        )

    def _get_wake_prefix(self, config_id: str) -> list:
        wake_prefix = self.config.get("wake_prefix", ["/"])
        config_id = config_id.strip()
        if config_id and self.core_lifecycle:
            config_mgr = getattr(self.core_lifecycle, "astrbot_config_mgr", None)
            if config_mgr and config_id in config_mgr.confs:
                return config_mgr.confs[config_id].get("wake_prefix", wake_prefix)
        return wake_prefix

    @staticmethod
    async def _get_command_payload(handler_full_name: str) -> dict:
        commands = await list_commands()
        for cmd in commands:
            if cmd["handler_full_name"] == handler_full_name:
                return cmd
        return {}

    @staticmethod
    def _payload(data: object) -> dict:
        return data if isinstance(data, dict) else {}
