import traceback
import aiohttp
from .route import Route, Response, RouteContext
from astrbot.core import logger
from quart import request
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.star_handler import EventType


class PluginRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
        plugin_manager: PluginManager,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/plugin/get": ("GET", self.get_plugins),
            "/plugin/install": ("POST", self.install_plugin),
            "/plugin/install-upload": ("POST", self.install_plugin_upload),
            "/plugin/update": ("POST", self.update_plugin),
            "/plugin/uninstall": ("POST", self.uninstall_plugin),
            "/plugin/market_list": ("GET", self.get_online_plugins),
            "/plugin/off": ("POST", self.off_plugin),
            "/plugin/on": ("POST", self.on_plugin),
            "/plugin/reload": ("POST", self.reload_plugins),
        }
        self.core_lifecycle = core_lifecycle
        self.plugin_manager = plugin_manager
        self.register_routes()

        self.translated_event_type = {
            EventType.AdapterMessageEvent: "平台消息下发时",
            EventType.OnLLMRequestEvent: "LLM 请求时",
            EventType.OnLLMResponseEvent: "LLM 响应后",
            EventType.OnDecoratingResultEvent: "回复消息前",
            EventType.OnCallingFuncToolEvent: "函数工具",
            EventType.OnAfterMessageSentEvent: "发送消息后",
        }

    async def reload_plugins(self):
        data = await request.json
        plugin_name = data.get("name", None)
        try:
            success, message = await self.plugin_manager.reload(plugin_name)
            if not success:
                return Response().error(message).__dict__
            return Response().ok(None, "重载成功。").__dict__
        except Exception as e:
            logger.error(f"/api/plugin/reload: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def get_online_plugins(self):
        custom = request.args.get("custom_registry")

        if custom:
            urls = [custom]
        else:
            urls = ["https://api.soulter.top/astrbot/plugins"]

        for url in urls:
            try:
                async with aiohttp.ClientSession(trust_env=True) as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            result = await response.json()
                            return Response().ok(result).__dict__
                        else:
                            logger.error(f"请求 {url} 失败，状态码：{response.status}")
            except Exception as e:
                logger.error(f"请求 {url} 失败，错误：{e}")

        return Response().error("获取插件列表失败").__dict__

    async def get_plugins(self):
        _plugin_resp = []
        for plugin in self.plugin_manager.context.get_all_stars():
            _t = {
                "name": plugin.name,
                "repo": "" if plugin.repo is None else plugin.repo,
                "author": plugin.author,
                "desc": plugin.desc,
                "version": plugin.version,
                "reserved": plugin.reserved,
                "activated": plugin.activated,
                "online_vesion": "",
                "handlers": await self.get_plugin_handlers_info(
                    plugin.star_handler_full_names
                ),
            }
            _plugin_resp.append(_t)
        return (
            Response()
            .ok(_plugin_resp, message=self.plugin_manager.failed_plugin_info)
            .__dict__
        )

    async def get_plugin_handlers_info(self, handler_full_names: list[str]):
        """解析插件行为"""
        handlers = []

        for handler_full_name in handler_full_names:
            info = {}
            handler = star_handlers_registry.star_handlers_map.get(
                handler_full_name, None
            )
            if handler is None:
                continue
            info["event_type"] = handler.event_type.name
            info["event_type_h"] = self.translated_event_type.get(
                handler.event_type, handler.event_type.name
            )
            info["handler_full_name"] = handler.handler_full_name
            info["desc"] = handler.desc
            info["handler_name"] = handler.handler_name

            if handler.event_type == EventType.AdapterMessageEvent:
                # 处理平台适配器消息事件
                has_admin = False
                for filter in (
                    handler.event_filters
                ):  # 正常handler就只有 1~2 个 filter，因此这里时间复杂度不会太高
                    if isinstance(filter, CommandFilter):
                        info["type"] = "指令"
                        info["cmd"] = (
                            f"{filter.parent_command_names[0]} {filter.command_name}"
                        )
                        info["cmd"] = info["cmd"].strip()
                        if (
                            self.core_lifecycle.astrbot_config["wake_prefix"]
                            and len(self.core_lifecycle.astrbot_config["wake_prefix"])
                            > 0
                        ):
                            info["cmd"] = (
                                f"{self.core_lifecycle.astrbot_config['wake_prefix'][0]}{info['cmd']}"
                            )
                    elif isinstance(filter, CommandGroupFilter):
                        info["type"] = "指令组"
                        info["cmd"] = filter.get_complete_command_names()[0]
                        info["cmd"] = info["cmd"].strip()
                        info["sub_command"] = filter.print_cmd_tree(
                            filter.sub_command_filters
                        )
                        if (
                            self.core_lifecycle.astrbot_config["wake_prefix"]
                            and len(self.core_lifecycle.astrbot_config["wake_prefix"])
                            > 0
                        ):
                            info["cmd"] = (
                                f"{self.core_lifecycle.astrbot_config['wake_prefix'][0]}{info['cmd']}"
                            )
                    elif isinstance(filter, RegexFilter):
                        info["type"] = "正则匹配"
                        info["cmd"] = filter.regex_str
                    elif isinstance(filter, PermissionTypeFilter):
                        has_admin = True
                info["has_admin"] = has_admin
                if "cmd" not in info:
                    info["cmd"] = "未知"
                if "type" not in info:
                    info["type"] = "事件监听器"
            else:
                info["cmd"] = "自动触发"
                info["type"] = "无"

            if not info["desc"]:
                info["desc"] = "无描述"

            handlers.append(info)

        return handlers

    async def install_plugin(self):
        post_data = await request.json
        repo_url = post_data["url"]

        proxy: str = post_data.get("proxy", None)
        if proxy:
            proxy = proxy.removesuffix("/")

        try:
            logger.info(f"正在安装插件 {repo_url}")
            await self.plugin_manager.install_plugin(repo_url, proxy)
            # self.core_lifecycle.restart()
            logger.info(f"安装插件 {repo_url} 成功。")
            return Response().ok(None, "安装成功。").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def install_plugin_upload(self):
        try:
            file = await request.files
            file = file["file"]
            logger.info(f"正在安装用户上传的插件 {file.filename}")
            file_path = f"data/temp/{file.filename}"
            await file.save(file_path)
            await self.plugin_manager.install_plugin_from_file(file_path)
            # self.core_lifecycle.restart()
            logger.info(f"安装插件 {file.filename} 成功")
            return Response().ok(None, "安装成功。").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def uninstall_plugin(self):
        post_data = await request.json
        plugin_name = post_data["name"]
        try:
            logger.info(f"正在卸载插件 {plugin_name}")
            await self.plugin_manager.uninstall_plugin(plugin_name)
            logger.info(f"卸载插件 {plugin_name} 成功")
            return Response().ok(None, "卸载成功").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def update_plugin(self):
        post_data = await request.json
        plugin_name = post_data["name"]
        proxy: str = post_data.get("proxy", None)
        try:
            logger.info(f"正在更新插件 {plugin_name}")
            await self.plugin_manager.update_plugin(plugin_name, proxy)
            # self.core_lifecycle.restart()
            await self.plugin_manager.reload(plugin_name)
            logger.info(f"更新插件 {plugin_name} 成功。")
            return Response().ok(None, "更新成功。").__dict__
        except Exception as e:
            logger.error(f"/api/plugin/update: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def off_plugin(self):
        post_data = await request.json
        plugin_name = post_data["name"]
        try:
            await self.plugin_manager.turn_off_plugin(plugin_name)
            logger.info(f"停用插件 {plugin_name} 。")
            return Response().ok(None, "停用成功。").__dict__
        except Exception as e:
            logger.error(f"/api/plugin/off: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def on_plugin(self):
        post_data = await request.json
        plugin_name = post_data["name"]
        try:
            await self.plugin_manager.turn_on_plugin(plugin_name)
            logger.info(f"启用插件 {plugin_name} 。")
            return Response().ok(None, "启用成功。").__dict__
        except Exception as e:
            logger.error(f"/api/plugin/on: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__
