from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core import DEMO_MODE, logger, t
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star_handler import StarHandlerMetadata, star_handlers_registry
from astrbot.core.star.star_manager import PluginManager


class PluginCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def plugin_ls(self, event: AstrMessageEvent) -> None:
        """获取已经安装的插件列表。"""
        parts = [t("builtin-stars-plugin-list-title")]
        for plugin in self.context.get_all_stars():
            line = t(
                "builtin-stars-plugin-list-line",
                name=plugin.name,
                author=plugin.author,
                desc=plugin.desc,
            )
            if not plugin.activated:
                line += t("builtin-stars-plugin-list-disabled-tag")
            parts.append(line + "\n")

        if len(parts) == 1:
            plugin_list_info = t("builtin-stars-plugin-list-empty")
        else:
            plugin_list_info = "".join(parts)

        plugin_list_info += t("builtin-stars-plugin-list-footer")
        event.set_result(
            MessageEventResult().message(f"{plugin_list_info}").use_t2i(False),
        )

    async def plugin_off(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """禁用插件"""
        if DEMO_MODE:
            event.set_result(
                MessageEventResult().message(t("builtin-stars-plugin-off-demo-mode"))
            )
            return
        if not plugin_name:
            event.set_result(
                MessageEventResult().message(t("builtin-stars-plugin-off-usage")),
            )
            return
        await self.context._star_manager.turn_off_plugin(plugin_name)  # type: ignore
        event.set_result(
            MessageEventResult().message(
                t("builtin-stars-plugin-off-success", plugin_name=plugin_name)
            )
        )

    async def plugin_on(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """启用插件"""
        if DEMO_MODE:
            event.set_result(
                MessageEventResult().message(t("builtin-stars-plugin-on-demo-mode"))
            )
            return
        if not plugin_name:
            event.set_result(
                MessageEventResult().message(t("builtin-stars-plugin-on-usage")),
            )
            return
        await self.context._star_manager.turn_on_plugin(plugin_name)  # type: ignore
        event.set_result(
            MessageEventResult().message(
                t("builtin-stars-plugin-on-success", plugin_name=plugin_name)
            )
        )

    async def plugin_get(self, event: AstrMessageEvent, plugin_repo: str = "") -> None:
        """安装插件"""
        if DEMO_MODE:
            event.set_result(
                MessageEventResult().message(t("builtin-stars-plugin-get-demo-mode"))
            )
            return
        if not plugin_repo:
            event.set_result(
                MessageEventResult().message(t("builtin-stars-plugin-get-usage")),
            )
            return
        logger.info(
            t("builtin-stars-plugin-get-install-start", plugin_repo=plugin_repo)
        )
        if self.context._star_manager:
            star_mgr: PluginManager = self.context._star_manager
            try:
                await star_mgr.install_plugin(plugin_repo)  # type: ignore
                event.set_result(
                    MessageEventResult().message(t("builtin-stars-plugin-get-success"))
                )
            except Exception as e:
                logger.error(t("builtin-stars-plugin-get-failed-log", error=str(e)))
                event.set_result(
                    MessageEventResult().message(
                        t("builtin-stars-plugin-get-failed-user", error=str(e))
                    )
                )
                return

    async def plugin_help(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """获取插件帮助"""
        if not plugin_name:
            event.set_result(
                MessageEventResult().message(t("builtin-stars-plugin-help-usage")),
            )
            return
        plugin = self.context.get_registered_star(plugin_name)
        if plugin is None:
            event.set_result(
                MessageEventResult().message(t("builtin-stars-plugin-help-not-found"))
            )
            return
        help_msg = ""
        help_msg += t(
            "builtin-stars-plugin-help-author-version",
            author=plugin.author,
            version=plugin.version,
        )
        command_handlers = []
        command_names = []
        for handler in star_handlers_registry:
            assert isinstance(handler, StarHandlerMetadata)
            if handler.handler_module_path != plugin.module_path:
                continue
            for filter_ in handler.event_filters:
                if isinstance(filter_, CommandFilter):
                    command_handlers.append(handler)
                    command_names.append(filter_.command_name)
                    break
                if isinstance(filter_, CommandGroupFilter):
                    command_handlers.append(handler)
                    command_names.append(filter_.group_name)

        if len(command_handlers) > 0:
            parts = [t("builtin-stars-plugin-help-command-list-title")]
            for i in range(len(command_handlers)):
                line = t(
                    "builtin-stars-plugin-help-command-line",
                    command_name=command_names[i],
                )
                if command_handlers[i].desc:
                    line = t(
                        "builtin-stars-plugin-help-command-line-with-desc",
                        command_name=command_names[i],
                        command_desc=command_handlers[i].desc,
                    )
                parts.append(line + "\n")
            parts.append(t("builtin-stars-plugin-help-command-tip"))
            help_msg += "".join(parts)

        ret = t("builtin-stars-plugin-help-title", plugin_name=plugin_name) + help_msg
        ret += t("builtin-stars-plugin-help-readme-tip")
        event.set_result(MessageEventResult().message(ret).use_t2i(False))
