import traceback
import aiohttp
import os
import json
from datetime import datetime

import ssl
import certifi

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
from astrbot.core import DEMO_MODE


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
            "/plugin/readme": ("GET", self.get_plugin_readme),
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
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

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
        force_refresh = request.args.get("force_refresh", "false").lower() == "true"

        cache_file = "data/plugins.json"

        if custom:
            urls = [custom]
        else:
            urls = [
                "https://api.soulter.top/astrbot/plugins",
                "https://github.com/AstrBotDevs/AstrBot_Plugins_Collection/raw/refs/heads/main/plugin_cache_original.json",
            ]

        # 如果不是强制刷新，先检查缓存是否有效
        cached_data = None
        if not force_refresh:
            # 先检查MD5是否匹配，如果匹配则使用缓存
            if await self._is_cache_valid(cache_file):
                cached_data = self._load_plugin_cache(cache_file)
                if cached_data:
                    logger.debug("缓存MD5匹配，使用缓存的插件市场数据")
                    return Response().ok(cached_data).__dict__

        # 尝试获取远程数据
        remote_data = None
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        for url in urls:
            try:
                async with aiohttp.ClientSession(
                    trust_env=True, connector=connector
                ) as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            remote_data = await response.json()

                            # 检查远程数据是否为空
                            if not remote_data or (
                                isinstance(remote_data, dict) and len(remote_data) == 0
                            ):
                                logger.warning(f"远程插件市场数据为空: {url}")
                                continue  # 继续尝试其他URL或使用缓存

                            logger.info("成功获取远程插件市场数据")
                            # 获取最新的MD5并保存到缓存
                            current_md5 = await self._get_remote_md5()
                            self._save_plugin_cache(
                                cache_file, remote_data, current_md5
                            )
                            return Response().ok(remote_data).__dict__
                        else:
                            logger.error(f"请求 {url} 失败，状态码：{response.status}")
            except Exception as e:
                logger.error(f"请求 {url} 失败，错误：{e}")

        # 如果远程获取失败，尝试使用缓存数据
        if not cached_data:
            cached_data = self._load_plugin_cache(cache_file)

        if cached_data:
            logger.warning("远程插件市场数据获取失败，使用缓存数据")
            return Response().ok(cached_data, "使用缓存数据，可能不是最新版本").__dict__

        return Response().error("获取插件列表失败，且没有可用的缓存数据").__dict__

    async def _is_cache_valid(self, cache_file: str) -> bool:
        """检查缓存是否有效（基于MD5）"""
        try:
            if not os.path.exists(cache_file):
                return False

            # 加载缓存文件
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            cached_md5 = cache_data.get("md5")
            if not cached_md5:
                logger.debug("缓存文件中没有MD5信息")
                return False

            # 获取远程MD5
            remote_md5 = await self._get_remote_md5()
            if not remote_md5:
                logger.warning("无法获取远程MD5，将使用缓存")
                return True  # 如果无法获取远程MD5，认为缓存有效

            is_valid = cached_md5 == remote_md5
            logger.debug(
                f"插件数据MD5: 本地={cached_md5}, 远程={remote_md5}, 有效={is_valid}"
            )
            return is_valid

        except Exception as e:
            logger.warning(f"检查缓存有效性失败: {e}")
            return False

    async def _get_remote_md5(self) -> str:
        """获取远程插件数据的MD5"""
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with aiohttp.ClientSession(
                trust_env=True, connector=connector
            ) as session:
                async with session.get(
                    "https://api.soulter.top/astrbot/plugins-md5"
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("md5", "")
                    else:
                        logger.error(f"获取MD5失败，状态码：{response.status}")
                        return ""
        except Exception as e:
            logger.error(f"获取远程MD5失败: {e}")
            return ""

    def _load_plugin_cache(self, cache_file: str):
        """加载本地缓存的插件市场数据"""
        try:
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    # 检查缓存是否有效
                    if "data" in cache_data and "timestamp" in cache_data:
                        logger.debug(
                            f"加载缓存文件: {cache_file}, 缓存时间: {cache_data['timestamp']}"
                        )
                        return cache_data["data"]
        except Exception as e:
            logger.warning(f"加载插件市场缓存失败: {e}")
        return None

    def _save_plugin_cache(self, cache_file: str, data, md5: str = None):
        """保存插件市场数据到本地缓存"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)

            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "data": data,
                "md5": md5 or "",
            }

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"插件市场数据已缓存到: {cache_file}, MD5: {md5}")
        except Exception as e:
            logger.warning(f"保存插件市场缓存失败: {e}")

    async def get_plugins(self):
        _plugin_resp = []
        plugin_name = request.args.get("name")
        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin_name and plugin.name != plugin_name:
                continue
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
                    elif isinstance(filter, CommandGroupFilter):
                        info["type"] = "指令组"
                        info["cmd"] = filter.get_complete_command_names()[0]
                        info["cmd"] = info["cmd"].strip()
                        info["sub_command"] = filter.print_cmd_tree(
                            filter.sub_command_filters
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
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.json
        repo_url = post_data["url"]

        proxy: str = post_data.get("proxy", None)
        if proxy:
            proxy = proxy.removesuffix("/")

        try:
            logger.info(f"正在安装插件 {repo_url}")
            plugin_info = await self.plugin_manager.install_plugin(repo_url, proxy)
            # self.core_lifecycle.restart()
            logger.info(f"安装插件 {repo_url} 成功。")
            return Response().ok(plugin_info, "安装成功。").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def install_plugin_upload(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        try:
            file = await request.files
            file = file["file"]
            logger.info(f"正在安装用户上传的插件 {file.filename}")
            file_path = f"data/temp/{file.filename}"
            await file.save(file_path)
            plugin_info = await self.plugin_manager.install_plugin_from_file(file_path)
            # self.core_lifecycle.restart()
            logger.info(f"安装插件 {file.filename} 成功")
            return Response().ok(plugin_info, "安装成功。").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def uninstall_plugin(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

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
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

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
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

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
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.json
        plugin_name = post_data["name"]
        try:
            await self.plugin_manager.turn_on_plugin(plugin_name)
            logger.info(f"启用插件 {plugin_name} 。")
            return Response().ok(None, "启用成功。").__dict__
        except Exception as e:
            logger.error(f"/api/plugin/on: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def get_plugin_readme(self):
        plugin_name = request.args.get("name")
        logger.debug(f"正在获取插件 {plugin_name} 的README文件内容")

        if not plugin_name:
            logger.warning("插件名称为空")
            return Response().error("插件名称不能为空").__dict__

        plugin_obj = None
        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin.name == plugin_name:
                plugin_obj = plugin
                break

        if not plugin_obj:
            logger.warning(f"插件 {plugin_name} 不存在")
            return Response().error(f"插件 {plugin_name} 不存在").__dict__

        plugin_dir = os.path.join(
            self.plugin_manager.plugin_store_path, plugin_obj.root_dir_name
        )

        if not os.path.isdir(plugin_dir):
            logger.warning(f"无法找到插件目录: {plugin_dir}")
            return Response().error(f"无法找到插件 {plugin_name} 的目录").__dict__

        readme_path = os.path.join(plugin_dir, "README.md")

        if not os.path.isfile(readme_path):
            logger.warning(f"插件 {plugin_name} 没有README文件")
            return Response().error(f"插件 {plugin_name} 没有README文件").__dict__

        try:
            with open(readme_path, "r", encoding="utf-8") as f:
                readme_content = f.read()

            return (
                Response()
                .ok({"content": readme_content}, "成功获取README内容")
                .__dict__
            )
        except Exception as e:
            logger.error(f"/api/plugin/readme: {traceback.format_exc()}")
            return Response().error(f"读取README文件失败: {str(e)}").__dict__
