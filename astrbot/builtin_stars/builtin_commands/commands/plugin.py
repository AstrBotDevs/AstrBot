from astrbot.core.lang import t
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core import DEMO_MODE, logger
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star_handler import StarHandlerMetadata, star_handlers_registry
from astrbot.core.star.star_manager import PluginManager


class PluginCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def plugin_ls(self, event: AstrMessageEvent) -> None:
        """获取已经安装的插件列表。"""
        parts = ["已加载的插件：\n"]
        for plugin in self.context.get_all_stars():
            line = f"- `{plugin.name}` By {plugin.author}: {plugin.desc}"
            if not plugin.activated:
                line += " (未启用)"
            parts.append(line + "\n")

        if len(parts) == 1:
            plugin_list_info = "没有加载任何插件。"
        else:
            plugin_list_info = "".join(parts)

        plugin_list_info += "\n使用 /plugin help <插件名> 查看插件帮助和加载的指令。\n使用 /plugin on/off <插件名> 启用或者禁用插件。"
        event.set_result(
            MessageEventResult().message(t("msg-9cae24f5", plugin_list_info=plugin_list_info)).use_t2i(False),
        )

    async def plugin_off(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """禁用插件"""
        if DEMO_MODE:
            event.set_result(MessageEventResult().message(t("msg-3f3a6087")))
            return
        if not plugin_name:
            event.set_result(
                MessageEventResult().message(t("msg-90e17cd4")),
            )
            return
        await self.context._star_manager.turn_off_plugin(plugin_name)  # type: ignore
        event.set_result(MessageEventResult().message(t("msg-d29d6d57", plugin_name=plugin_name)))

    async def plugin_on(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """启用插件"""
        if DEMO_MODE:
            event.set_result(MessageEventResult().message(t("msg-f90bbe20")))
            return
        if not plugin_name:
            event.set_result(
                MessageEventResult().message(t("msg-b897048f")),
            )
            return
        await self.context._star_manager.turn_on_plugin(plugin_name)  # type: ignore
        event.set_result(MessageEventResult().message(t("msg-ebfb93bb", plugin_name=plugin_name)))

    async def plugin_get(self, event: AstrMessageEvent, plugin_repo: str = "") -> None:
        """安装插件"""
        if DEMO_MODE:
            event.set_result(MessageEventResult().message(t("msg-9cd74a8d")))
            return
        if not plugin_repo:
            event.set_result(
                MessageEventResult().message(t("msg-d79ad78d")),
            )
            return
        logger.info(t("msg-4f293fe1", plugin_repo=plugin_repo))
        if self.context._star_manager:
            star_mgr: PluginManager = self.context._star_manager
            try:
                await star_mgr.install_plugin(plugin_repo)  # type: ignore
                event.set_result(MessageEventResult().message(t("msg-d40e7065")))
            except Exception as e:
                logger.error(t("msg-feff82c6", e=e))
                event.set_result(MessageEventResult().message(t("msg-feff82c6", e=e)))
                return

    async def plugin_help(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """获取插件帮助"""
        if not plugin_name:
            event.set_result(
                MessageEventResult().message(t("msg-5bfe9d3d")),
            )
            return
        plugin = self.context.get_registered_star(plugin_name)
        if plugin is None:
            event.set_result(MessageEventResult().message(t("msg-02627a9b")))
            return
        help_msg = ""
        help_msg += f"\n\n✨ 作者: {plugin.author}\n✨ 版本: {plugin.version}"
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
            parts = ["\n\n🔧 指令列表：\n"]
            for i in range(len(command_handlers)):
                line = f"- {command_names[i]}"
                if command_handlers[i].desc:
                    line += f": {command_handlers[i].desc}"
                parts.append(line + "\n")
            parts.append("\nTip: 指令的触发需要添加唤醒前缀，默认为 /。")
            help_msg += "".join(parts)

        ret = f"🧩 插件 {plugin_name} 帮助信息：\n" + help_msg
        ret += "更多帮助信息请查看插件仓库 README。"
        event.set_result(MessageEventResult().message(t("msg-ed8dcc22", ret=ret)).use_t2i(False))
