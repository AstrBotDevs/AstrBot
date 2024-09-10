import aiohttp

from model.command.manager import CommandManager
from model.plugin.manager import PluginManager
from type.message_event import AstrMessageEvent
from type.command import CommandResult
from type.types import Context
from type.config import VERSION
from SparkleLogging.utils.core import LogManager
from logging import Logger
from util.agent.web_searcher import search_from_bing, fetch_website_content

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class InternalCommandHandler:
    def __init__(self, manager: CommandManager, plugin_manager: PluginManager) -> None:
        self.manager = manager
        self.plugin_manager = plugin_manager
        
        self.manager.register("help", "查看帮助", 10, self.help)
        self.manager.register("wake", "设置机器人唤醒词", 10, self.set_nick)
        self.manager.register("update", "更新 AstrBot", 10, self.update)
        self.manager.register("plugin", "插件管理", 10, self.plugin)
        self.manager.register("reboot", "重启 AstrBot", 10, self.reboot)
        self.manager.register("websearch", "网页搜索开关", 10, self.web_search)
        self.manager.register("t2i", "文本转图片开关", 10, self.t2i_toggle)
        self.manager.register("myid", "获取你在此平台上的ID", 10, self.myid)
        self.manager.register("provider", "查看和切换当前使用的 LLM 资源来源", 10, self.provider)
        
    def provider(self, message: AstrMessageEvent, context: Context):
        if len(context.llms) == 0:
            return CommandResult().message("当前没有加载任何 LLM 资源。")

        tokens = self.manager.command_parser.parse(message.message_str)
        
        if tokens.len == 1:
            ret = "## 当前载入的 LLM 资源\n"
            for idx, llm in enumerate(context.llms):
                ret += f"{idx}. {llm.llm_name}"
                if llm.origin:
                    ret += f" (来源: {llm.origin})"
                if context.message_handler.provider == llm.llm_instance:
                    ret += " (当前使用)"
                ret += "\n"
            
            ret += "\n使用 provider <序号> 切换 LLM 资源。" 
            return CommandResult().message(ret)
        else:
            try:
                idx = int(tokens.get(1))
                if idx >= len(context.llms):
                    return CommandResult().message("provider: 无效的序号。")
                context.message_handler.set_provider(context.llms[idx].llm_instance)
                return CommandResult().message(f"已经成功切换到 LLM 资源 {context.llms[idx].llm_name}。")
            except BaseException as e:
                return CommandResult().message("provider: 参数错误。")

    def set_nick(self, message: AstrMessageEvent, context: Context):
        message_str = message.message_str
        if message.role != "admin":
            return CommandResult().message("你没有权限使用该指令。")
        l = message_str.split(" ")
        if len(l) == 1:
            return CommandResult().message(f"设置机器人唤醒词。以唤醒词开头的消息会唤醒机器人处理，起到 @ 的效果。\n示例：wake 昵称。当前唤醒词是：{context.config_helper.wake_prefix[0]}")
        nick = l[1].strip()
        if not nick:
            return CommandResult().message("wake: 请指定唤醒词。")
        context.config_helper.wake_prefix = [nick]
        context.config_helper.save_config()
        return CommandResult(
            hit=True,
            success=True,
            message_chain=f"已经成功将唤醒词设定为 {nick}。",
        )
        
    def update(self, message: AstrMessageEvent, context: Context):
        tokens = self.manager.command_parser.parse(message.message_str)
        if message.role != "admin":
            return CommandResult(
                hit=True,
                success=False,
                message_chain="你没有权限使用该指令",
            )
        update_info = context.updator.check_update(None, None)
        if tokens.len == 1:
            ret = ""
            if not update_info:
                ret = f"当前已经是最新版本 v{VERSION}。"
            else:
                ret = f"发现新版本 {update_info.version}，更新内容如下:\n---\n{update_info.body}\n---\n- 使用 /update latest 更新到最新版本。\n- 使用 /update vX.X.X 更新到指定版本。"
            return CommandResult().message(ret)
        else:
            if tokens.get(1) == "latest":
                try:
                    context.updator.update()
                    return CommandResult().message(f"已经成功更新到最新版本 v{update_info.version}。要应用更新，请重启 AstrBot。输入 /reboot 即可重启")
                except BaseException as e:
                    return CommandResult().message(f"更新失败。原因：{str(e)}")
            elif tokens.get(1).startswith("v"):
                try:
                    context.updator.update(version=tokens.get(1))
                    return CommandResult().message(f"已经成功更新到版本 v{tokens.get(1)}。要应用更新，请重启 AstrBot。输入 /reboot 即可重启")
                except BaseException as e:
                    return CommandResult().message(f"更新失败。原因：{str(e)}")
            else:
                return CommandResult().message("update: 参数错误。")
            
    def reboot(self, message: AstrMessageEvent, context: Context):
        if message.role != "admin":
            return CommandResult(
                hit=True,
                success=False,
                message_chain="你没有权限使用该指令",
            )
        context.updator._reboot(3, context)
        return CommandResult(
            hit=True,
            success=True,
            message_chain="AstrBot 将在 3s 后重启。",
        )
    
    def plugin(self, message: AstrMessageEvent, context: Context):
        tokens = self.manager.command_parser.parse(message.message_str)
        if tokens.len == 1:
            ret = "# 插件指令面板 \n- 安装插件: `plugin i 插件Github地址`\n- 卸载插件: `plugin d 插件名`\n- 查看插件列表：`plugin l`\n - 更新插件: `plugin u 插件名`\n"
            return CommandResult().message(ret)
        
        if tokens.get(1) == "l":
            plugin_list_info = ""
            for plugin in context.cached_plugins:
                plugin_list_info += f"- `{plugin.metadata.plugin_name}` By {plugin.metadata.author}: {plugin.metadata.desc}\n"
            if plugin_list_info.strip() == "":
                return CommandResult().message("plugin v: 没有找到插件。")
            return CommandResult().message(plugin_list_info)
        
        elif tokens.get(1) == "d":
            if message.role != "admin":
                return CommandResult().message("plugin d: 你没有权限使用该指令。")
            if tokens.len == 2:
                return CommandResult().message("plugin d: 请指定要卸载的插件名。")
            plugin_name = tokens.get(2)
            try:
                self.plugin_manager.uninstall_plugin(plugin_name)
            except BaseException as e:
                return CommandResult().message(f"plugin d: 卸载插件失败。原因：{str(e)}")
            return CommandResult().message(f"plugin d: 已经成功卸载插件 {plugin_name}。")
        
        elif tokens.get(1) == "i":
            if message.role != "admin":
                return CommandResult().message("plugin i: 你没有权限使用该指令。")
            if tokens.len == 2:
                return CommandResult().message("plugin i: 请指定要安装的插件的 Github 地址，或者前往可视化面板安装。")
            plugin_url = tokens.get(2)
            try:
                self.plugin_manager.install_plugin(plugin_url)
            except BaseException as e:
                return CommandResult().message(f"plugin i: 安装插件失败。原因：{str(e)}")
            return CommandResult().message("plugin i: 已经成功安装插件。")
        
        elif tokens.get(1) == "u":
            if message.role != "admin":
                return CommandResult().message("plugin u: 你没有权限使用该指令。")
            if tokens.len == 2:
                return CommandResult().message("plugin u: 请指定要更新的插件名。")
            plugin_name = tokens.get(2)
            try:
                self.plugin_manager.update_plugin(plugin_name)
            except BaseException as e:
                return CommandResult().message(f"plugin u: 更新插件失败。原因：{str(e)}")
            return CommandResult().message(f"plugin u: 已经成功更新插件 {plugin_name}。")
        
        return CommandResult().message("plugin: 参数错误。")

    async def help(self, message: AstrMessageEvent, context: Context):
        notice = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://soulter.top/channelbot/notice.json") as resp:
                    notice = (await resp.json())["notice"]
        except BaseException as e:
            logger.warning("An error occurred while fetching astrbot notice. Never mind, it's not important.")

        msg = "# Help Center\n## 指令列表\n"
        for key, value in self.manager.commands_handler.items():
            if value.plugin_metadata:
                msg += f"- `{key}` ({value.plugin_metadata.plugin_name}): {value.description}\n"
            else: msg += f"- `{key}`: {value.description}\n"
        # plugins
        if context.cached_plugins != None:
            plugin_list_info = ""
            for plugin in context.cached_plugins:
                plugin_list_info += f"- `{plugin.metadata.plugin_name}` {plugin.metadata.desc}\n"
            if plugin_list_info.strip() != "":
                msg += "\n## 插件列表\n> 使用plugin v 插件名 查看插件帮助\n"
                msg += plugin_list_info
        msg += notice

        return CommandResult().message(msg)

    def web_search(self, message: AstrMessageEvent, context: Context):
        l = message.message_str.split(' ')
        if len(l) == 1:
            return CommandResult(
                hit=True,
                success=True,
                message_chain=f"网页搜索功能当前状态: {context.config_helper.llm_settings.web_search}",
            )
        elif l[1] == 'on':
            context.config_helper.llm_settings.web_search = True
            context.config_helper.save_config()
            context.register_llm_tool("web_search", [{
                "type": "string",
                "name": "keyword",
                "description": "搜索关键词"
            }],
                "通过搜索引擎搜索。如果问题需要获取近期、实时的消息，在网页上搜索(如天气、新闻或任何需要通过网页获取信息的问题)，则调用此函数；如果没有，不要调用此函数。",
                search_from_bing
            )
            context.register_llm_tool("fetch_website_content", [{
                "type": "string",
                "name": "url",
                "description": "要获取内容的网页链接"
            }],
                "获取网页的内容。如果问题带有合法的网页链接并且用户有需求了解网页内容(例如: `帮我总结一下 https://github.com 的内容`), 就调用此函数。如果没有，不要调用此函数。",
                fetch_website_content
            )
            
            return CommandResult(
                hit=True,
                success=True,
                message_chain="已开启网页搜索",
            )
        elif l[1] == 'off':
            context.config_helper.llm_settings.web_search = False
            context.config_helper.save_config()
            context.unregister_llm_tool("web_search")
            context.unregister_llm_tool("fetch_website_content")
            
            return CommandResult(
                hit=True,
                success=True,
                message_chain="已关闭网页搜索",
            )
        else:
            return CommandResult(
                hit=True,
                success=False,
                message_chain="参数错误",
            )
    
    def t2i_toggle(self, message: AstrMessageEvent, context: Context):
        p = context.config_helper.t2i
        if p:
            context.config_helper.t2i = False
            context.config_helper.save_config()
            return CommandResult(
                hit=True,
                success=True,
                message_chain="已关闭文本转图片模式。",
            )
        context.config_helper.t2i = True
        context.config_helper.save_config()
        
        return CommandResult(
            hit=True,
            success=True,
            message_chain="已开启文本转图片模式。",
        )
        
    def myid(self, message: AstrMessageEvent, context: Context):
        try:
            user_id = str(message.message_obj.sender.user_id)
            return CommandResult(
                hit=True,
                success=True,
                message_chain=f"你在此平台上的ID：{user_id}",
            )
        except BaseException as e:
            return CommandResult(
                hit=True,
                success=False,
                message_chain=f"在 {message.platform} 上获取你的ID失败，原因: {str(e)}",
            )
