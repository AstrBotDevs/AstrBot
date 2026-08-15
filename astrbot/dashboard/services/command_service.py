from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db.protocols import CommandStore
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.star.command_management import (
    list_command_conflicts,
    list_commands,
    rename_command,
    toggle_command,
    update_command_permission,
)
from astrbot.core.star.plugin_catalog import PluginCatalog
from astrbot.core.star.star_handler import HandlerRegistry
from astrbot.core.utils.shared_preferences import SharedPreferences


class CommandServiceError(Exception):
    pass


class CommandService:
    def __init__(
        self,
        config: AstrBotConfig,
        db: CommandStore,
        preferences: SharedPreferences,
        handler_registry: HandlerRegistry,
        plugin_catalog: PluginCatalog,
        platform_manager: PlatformManager,
        config_manager: AstrBotConfigManager,
    ) -> None:
        self.config = config
        self.db = db
        self.preferences = preferences
        self.handler_registry = handler_registry
        self.plugin_catalog = plugin_catalog
        self.platform_manager = platform_manager
        self.config_manager = config_manager

    async def _refresh_command_surfaces(self) -> None:
        self.plugin_catalog.refresh_command_catalogs()
        await self.platform_manager.refresh_registered_commands()

    async def list_commands(self, config_id: str = "") -> dict:
        commands = await list_commands(self.db, self.handler_registry)
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

    async def list_conflicts(self):
        return await list_command_conflicts(
            self.db,
            self.handler_registry,
        )

    async def toggle_command(self, handler_full_name: str | None, enabled) -> dict:
        if handler_full_name is None or enabled is None:
            raise CommandServiceError("handler_full_name 与 enabled 均为必填。")

        if isinstance(enabled, str):
            enabled = enabled.lower() in ("1", "true", "yes", "on")

        try:
            await toggle_command(
                self.db,
                self.handler_registry,
                handler_full_name,
                bool(enabled),
            )
        except ValueError as exc:
            raise CommandServiceError(str(exc)) from exc

        await self._refresh_command_surfaces()
        return await self._get_command_payload(handler_full_name)

    async def bulk_toggle_builtin_commands(self, enabled: bool) -> dict:
        """Set enabled state for every built-in command in the command DB."""
        db = self.db
        commands = await list_commands(db, self.handler_registry)
        updated: list[str] = []
        for command in self._iter_commands(commands):
            if (
                command.get("module_path")
                != "astrbot.builtin_stars.builtin_commands.main"
            ):
                continue
            handler_full_name = command.get("handler_full_name")
            if not isinstance(handler_full_name, str):
                continue
            await toggle_command(
                db,
                self.handler_registry,
                handler_full_name,
                enabled,
            )
            updated.append(handler_full_name)
        await self._refresh_command_surfaces()
        return {"enabled": enabled, "updated": updated}

    async def rename_command(
        self,
        handler_full_name: str | None,
        new_name: str | None,
        aliases=None,
    ) -> dict:
        if not handler_full_name or not new_name:
            raise CommandServiceError("handler_full_name 与 new_name 均为必填。")

        try:
            await rename_command(
                self.db,
                self.handler_registry,
                handler_full_name,
                new_name,
                aliases=aliases,
            )
        except ValueError as exc:
            raise CommandServiceError(str(exc)) from exc

        await self._refresh_command_surfaces()
        return await self._get_command_payload(handler_full_name)

    async def update_permission(
        self,
        handler_full_name: str | None,
        action: str | None,
    ) -> dict:
        if not handler_full_name or not action:
            raise CommandServiceError("handler_full_name 与 action 均为必填。")

        try:
            await update_command_permission(
                self.preferences,
                self.handler_registry,
                handler_full_name,
                action,
            )
        except ValueError as exc:
            raise CommandServiceError(str(exc)) from exc

        return await self._get_command_payload(handler_full_name)

    def _get_wake_prefix(self, config_id: str) -> list:
        wake_prefix = self.config.get("wake_prefix", ["/"])
        config_id = config_id.strip()
        if config_id and config_id in self.config_manager.confs:
            return self.config_manager.confs[config_id].get("wake_prefix", wake_prefix)
        return wake_prefix

    async def _get_command_payload(self, handler_full_name: str) -> dict:
        commands = await list_commands(self.db, self.handler_registry)
        for cmd in commands:
            found = CommandService._find_command_payload(cmd, handler_full_name)
            if found:
                return found
        return {}

    @staticmethod
    def _iter_commands(commands: list[dict]):
        for command in commands:
            yield command
            yield from CommandService._iter_commands(command.get("sub_commands", []))

    @staticmethod
    def _find_command_payload(command: dict, handler_full_name: str) -> dict | None:
        if command.get("handler_full_name") == handler_full_name:
            return command

        for sub_command in command.get("sub_commands", []):
            found = CommandService._find_command_payload(
                sub_command,
                handler_full_name,
            )
            if found:
                return found

        return None
