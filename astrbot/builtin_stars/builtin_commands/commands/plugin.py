from astrbot.api import logger, safe_error, star
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n


class PluginCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def list_plugins(self, event: AstrMessageEvent) -> None:
        """List loaded plugins."""
        parts: list[str] = []
        disabled_label = await self.context.i18n.t(event, "plugin.list.disabled")
        for plugin in self.context.runtime_info.plugins():
            suffix = f" {disabled_label}" if not plugin.active else ""
            parts.append(
                await self.context.i18n.t(
                    event,
                    "plugin.list.item",
                    name=plugin.name,
                    author=plugin.author,
                    description=plugin.description,
                    suffix=suffix,
                )
            )
        listing = (
            "".join(parts)
            if parts
            else await self.context.i18n.t(event, "plugin.list.empty")
        )
        await reply_i18n(
            self.context,
            event,
            "plugin.list.body",
            listing=listing,
        )

    async def disable(self, event: AstrMessageEvent, plugin_name: str) -> None:
        """Disable a plugin."""
        if self.context.runtime_info.demo_mode:
            await reply_i18n(self.context, event, "plugin.disable.demo")
            return
        try:
            await self.context.runtime_info.disable_plugin(plugin_name)
        except RuntimeError:
            await reply_i18n(self.context, event, "plugin.disable.unavailable")
            return
        await reply_i18n(
            self.context, event, "plugin.disable.ok", plugin_name=plugin_name
        )

    async def enable(self, event: AstrMessageEvent, plugin_name: str) -> None:
        """Enable a plugin."""
        if self.context.runtime_info.demo_mode:
            await reply_i18n(self.context, event, "plugin.enable.demo")
            return
        try:
            await self.context.runtime_info.enable_plugin(plugin_name)
        except RuntimeError:
            await reply_i18n(self.context, event, "plugin.enable.unavailable")
            return
        await reply_i18n(
            self.context, event, "plugin.enable.ok", plugin_name=plugin_name
        )

    async def install(self, event: AstrMessageEvent, plugin_repo: str) -> None:
        """Install a plugin from a repo URL."""
        if self.context.runtime_info.demo_mode:
            await reply_i18n(self.context, event, "plugin.install.demo")
            return
        logger.info("Preparing to install plugin from %s", plugin_repo)
        try:
            await self.context.runtime_info.install_plugin(plugin_repo)
        except RuntimeError:
            await reply_i18n(self.context, event, "plugin.install.unavailable")
            return
        except Exception as exc:
            logger.error("Plugin installation failed: %s", exc)
            await reply_i18n(
                self.context,
                event,
                "plugin.install.failed",
                error=safe_error("", exc),
            )
            return
        await reply_i18n(self.context, event, "plugin.install.ok")

    async def show(
        self,
        event: AstrMessageEvent,
        plugin_name: str,
    ) -> None:
        """Show plugin metadata and commands."""
        plugin = self.context.runtime_info.plugin(plugin_name)
        if plugin is None:
            await reply_i18n(self.context, event, "plugin.show.missing")
            return

        help_msg = await self.context.i18n.t(
            event,
            "plugin.show.meta",
            author=plugin.author,
            version=plugin.version,
        )
        command_entries = self.context.runtime_info.commands_for_plugin(plugin_name)
        if command_entries:
            parts = [await self.context.i18n.t(event, "plugin.show.commands")]
            for command in command_entries:
                if command.description:
                    parts.append(
                        await self.context.i18n.t(
                            event,
                            "plugin.show.command",
                            invocation=command.invocation,
                            description=command.description,
                        )
                    )
                else:
                    parts.append(
                        await self.context.i18n.t(
                            event,
                            "plugin.show.command_plain",
                            invocation=command.invocation,
                        )
                    )
            parts.append(await self.context.i18n.t(event, "plugin.show.tip"))
            help_msg += "".join(parts)
        await reply_i18n(
            self.context,
            event,
            "plugin.show.body",
            plugin_name=plugin_name,
            help_msg=help_msg,
        )
