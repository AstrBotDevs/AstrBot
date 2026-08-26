from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db.protocols import CommandStore
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.star.command_management import (
    apply_path_winners,
    list_command_conflicts,
    list_commands,
    rename_command,
    takeover_command,
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
        await apply_path_winners(
            self.db,
            self.plugin_catalog,
            self.config_manager.confs,
        )
        self.plugin_catalog.refresh_command_catalogs()
        await self.platform_manager.refresh_registered_commands()

    async def list_commands(self, config_id: str = "") -> dict:
        commands = await list_commands(
            self.db,
            self.handler_registry,
            self._plugin_scope(config_id),
        )
        summary = {
            "total": len(commands),
            "disabled": len([cmd for cmd in commands if not cmd["enabled"]]),
            "conflicts": len([cmd for cmd in commands if cmd.get("has_conflict")]),
        }
        command_prefixes, llm_prefixes = self._get_prefixes(config_id)
        return {
            "items": commands,
            "summary": summary,
            "command_prefixes": command_prefixes,
            "llm_access": {"prefixes": llm_prefixes},
        }

    async def list_conflicts(self, config_id: str = ""):
        return await list_command_conflicts(
            self.db,
            self.handler_registry,
            config_id=config_id,
            plugin_names=self._plugin_scope(config_id),
        )

    async def takeover_command(
        self,
        command_id: str | None,
        config_id: str = "",
    ) -> dict:
        if not command_id:
            raise CommandServiceError("command_id 为必填。")
        try:
            await takeover_command(
                self.db,
                self.handler_registry,
                command_id,
                config_id=config_id,
            )
        except ValueError as exc:
            raise CommandServiceError(str(exc)) from exc
        await self._refresh_command_surfaces()
        return await self._get_command_payload(command_id)

    async def toggle_command(self, command_id: str | None, enabled) -> dict:
        if command_id is None or enabled is None:
            raise CommandServiceError("command_id 与 enabled 均为必填。")

        if isinstance(enabled, str):
            enabled = enabled.lower() in ("1", "true", "yes", "on")

        try:
            await toggle_command(
                self.db,
                self.handler_registry,
                command_id,
                bool(enabled),
            )
        except ValueError as exc:
            raise CommandServiceError(str(exc)) from exc

        await self._refresh_command_surfaces()
        return await self._get_command_payload(command_id)

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
            command_id = command.get("command_id")
            if not isinstance(command_id, str):
                continue
            await toggle_command(
                db,
                self.handler_registry,
                command_id,
                enabled,
            )
            updated.append(command_id)
        await self._refresh_command_surfaces()
        return {"enabled": enabled, "updated": updated}

    async def rename_command(
        self,
        command_id: str | None,
        new_name: str | None,
        aliases=None,
        *,
        config_id: str = "",
    ) -> dict:
        if not command_id or not new_name:
            raise CommandServiceError("command_id 与 new_name 均为必填。")

        try:
            await rename_command(
                self.db,
                self.handler_registry,
                command_id,
                new_name,
                aliases=aliases,
                config_id=config_id,
                config=self._config_for_id(config_id),
            )
        except ValueError as exc:
            raise CommandServiceError(str(exc)) from exc

        await self._refresh_command_surfaces()
        return await self._get_command_payload(command_id)

    def _config_for_id(self, config_id: str) -> dict:
        """Return the selected routing profile for occupancy validation."""
        config_id = config_id.strip()
        if config_id and config_id in self.config_manager.confs:
            return self.config_manager.confs[config_id]
        return self.config

    def _plugin_scope(self, config_id: str) -> set[str] | None:
        config = self._config_for_id(config_id)
        raw = config.get("plugin_set", ["*"])
        if raw == ["*"] or raw is None:
            return None
        return {str(name) for name in raw if str(name).strip()}

    async def update_permission(
        self,
        command_id: str | None,
        action: str | None,
    ) -> dict:
        if not command_id or not action:
            raise CommandServiceError("command_id 与 action 均为必填。")

        try:
            await update_command_permission(
                self.preferences,
                self.handler_registry,
                command_id,
                action,
            )
        except ValueError as exc:
            raise CommandServiceError(str(exc)) from exc

        return await self._get_command_payload(command_id)

    def _get_prefixes(self, config_id: str) -> tuple[list, list]:
        command_prefixes = list(self.config.get("command_prefixes", ["/"]))
        llm_prefixes = list(
            (self.config.get("llm_access") or {}).get("prefixes", ["/"])
        )
        config_id = config_id.strip()
        if config_id and config_id in self.config_manager.confs:
            scoped = self.config_manager.confs[config_id]
            command_prefixes = list(scoped.get("command_prefixes", command_prefixes))
            llm_prefixes = list(
                (scoped.get("llm_access") or {}).get("prefixes", llm_prefixes)
            )
        return command_prefixes, llm_prefixes

    async def _get_command_payload(self, command_id: str) -> dict:
        commands = await list_commands(self.db, self.handler_registry)
        for cmd in commands:
            found = CommandService._find_command_payload(cmd, command_id)
            if found:
                return found
        return {}

    @staticmethod
    def _iter_commands(commands: list[dict]):
        for command in commands:
            yield command
            yield from CommandService._iter_commands(command.get("sub_commands", []))

    @staticmethod
    def _find_command_payload(command: dict, command_id: str) -> dict | None:
        if command.get("command_id") == command_id:
            return command

        for sub_command in command.get("sub_commands", []):
            found = CommandService._find_command_payload(
                sub_command,
                command_id,
            )
            if found:
                return found

        return None
