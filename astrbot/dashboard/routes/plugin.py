import asyncio
import hashlib
import json
import os
import ssl
import traceback
from dataclasses import dataclass
from datetime import datetime

import aiohttp
import certifi
from quart import request

from astrbot.api import sp
from astrbot.core import DEMO_MODE, file_token_service, logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_temp_path,
)

from .route import Response, Route, RouteContext

PLUGIN_UPDATE_CONCURRENCY = (
    3  # limit concurrent updates to avoid overwhelming plugin sources
)


@dataclass
class RegistrySource:
    urls: list[str]
    cache_file: str
    md5_url: str | None  # None means "no remote MD5, always treat cache as stale"


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
            "/plugin/update-all": ("POST", self.update_all_plugins),
            "/plugin/uninstall": ("POST", self.uninstall_plugin),
            "/plugin/market_list": ("GET", self.get_online_plugins),
            "/plugin/off": ("POST", self.off_plugin),
            "/plugin/on": ("POST", self.on_plugin),
            "/plugin/reload-failed": ("POST", self.reload_failed_plugins),
            "/plugin/reload": ("POST", self.reload_plugins),
            "/plugin/readme": ("GET", self.get_plugin_readme),
            "/plugin/changelog": ("GET", self.get_plugin_changelog),
            "/plugin/source/get": ("GET", self.get_custom_source),
            "/plugin/source/save": ("POST", self.save_custom_source),
            "/plugin/source/get-failed-plugins": ("GET", self.get_failed_plugins),
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
            EventType.OnPluginErrorEvent: "插件报错时",
        }

        self._logo_cache = {}

    async def reload_failed_plugins(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        try:
            data = await request.get_json()
            dir_name = data.get("dir_name")  # 这里拿的是目录名，不是插件名

            if not dir_name:
                return Response().error("缺少插件目录名").__dict__

            # 调用 star_manager.py 中的函数
            # 注意：传入的是目录名
            success, err = await self.plugin_manager.reload_failed_plugin(dir_name)

            if success:
                return Response().ok(None, f"插件 {dir_name} 重载成功。").__dict__
            else:
                return Response().error(f"重载失败: {err}").__dict__

        except Exception as e:
            logger.error(f"/api/plugin/reload-failed: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def reload_plugins(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        data = await request.get_json()
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

        # 构建注册表源信息
        source = self._build_registry_source(custom)

        # 如果不是强制刷新，先检查缓存是否有效
        cached_data = None
        if not force_refresh:
            # 先检查MD5是否匹配，如果匹配则使用缓存
            if await self._is_cache_valid(source):
                cached_data = self._load_plugin_cache(source.cache_file)
                if cached_data:
                    logger.debug("缓存MD5匹配，使用缓存的插件市场数据")
                    return Response().ok(cached_data).__dict__

        # 尝试获取远程数据
        remote_data = None
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        for url in source.urls:
            try:
                async with (
                    aiohttp.ClientSession(
                        trust_env=True,
                        connector=connector,
                    ) as session,
                    session.get(url) as response,
                ):
                    if response.status == 200:
                        try:
                            remote_data = await response.json()
                        except aiohttp.ContentTypeError:
                            remote_text = await response.text()
                            remote_data = json.loads(remote_text)

                        # 检查远程数据是否为空
                        if not remote_data or (
                            isinstance(remote_data, dict) and len(remote_data) == 0
                        ):
                            logger.warning(f"远程插件市场数据为空: {url}")
                            continue  # 继续尝试其他URL或使用缓存

                        logger.info(
                            f"成功获取远程插件市场数据，包含 {len(remote_data)} 个插件"
                        )
                        # 获取最新的MD5并保存到缓存
                        current_md5 = await self._fetch_remote_md5(source.md5_url)
                        self._save_plugin_cache(
                            source.cache_file,
                            remote_data,
                            current_md5,
                        )
                        return Response().ok(remote_data).__dict__
                    logger.error(f"请求 {url} 失败，状态码：{response.status}")
            except Exception as e:
                logger.error(f"请求 {url} 失败，错误：{e}")

        # 如果远程获取失败，尝试使用缓存数据
        if not cached_data:
            cached_data = self._load_plugin_cache(source.cache_file)

        if cached_data:
            logger.warning("远程插件市场数据获取失败，使用缓存数据")
            return Response().ok(cached_data, "使用缓存数据，可能不是最新版本").__dict__

        return Response().error("获取插件列表失败，且没有可用的缓存数据").__dict__

    def _build_registry_source(self, custom_url: str | None) -> RegistrySource:
        """构建注册表源信息"""
        data_dir = get_astrbot_data_path()
        if custom_url:
            # 对自定义URL生成一个安全的文件名
            url_hash = hashlib.md5(custom_url.encode()).hexdigest()[:8]
            cache_file = os.path.join(data_dir, f"plugins_custom_{url_hash}.json")

            # 更安全的后缀处理方式
            if custom_url.endswith(".json"):
                md5_url = custom_url[:-5] + "-md5.json"
            else:
                md5_url = custom_url + "-md5.json"

            urls = [custom_url]
        else:
            cache_file = os.path.join(data_dir, "plugins.json")
            md5_url = "https://api.soulter.top/astrbot/plugins-md5"
            urls = [
                "https://api.soulter.top/astrbot/plugins",
                "https://github.com/AstrBotDevs/AstrBot_Plugins_Collection/raw/refs/heads/main/plugin_cache_original.json",
            ]
        return RegistrySource(urls=urls, cache_file=cache_file, md5_url=md5_url)

    def _load_cached_md5(self, cache_file: str) -> str | None:
        """从缓存文件中加载MD5"""
        if not os.path.exists(cache_file):
            return None

        try:
            with open(cache_file, encoding="utf-8") as f:
                cache_data = json.load(f)
            return cache_data.get("md5")
        except Exception as e:
            logger.warning(f"加载缓存MD5失败: {e}")
            return None

    async def _fetch_remote_md5(self, md5_url: str | None) -> str | None:
        """获取远程MD5"""
        if not md5_url:
            return None

        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with (
                aiohttp.ClientSession(
                    trust_env=True,
                    connector=connector,
                ) as session,
                session.get(md5_url) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    return data.get("md5", "")
        except Exception as e:
            logger.debug(f"获取远程MD5失败: {e}")
        return None

    async def _is_cache_valid(self, source: RegistrySource) -> bool:
        """检查缓存是否有效（基于MD5）"""
        try:
            cached_md5 = self._load_cached_md5(source.cache_file)
            if not cached_md5:
                logger.debug("缓存文件中没有MD5信息")
                return False

            remote_md5 = await self._fetch_remote_md5(source.md5_url)
            if remote_md5 is None:
                logger.warning("无法获取远程MD5，将使用缓存")
                return True  # 如果无法获取远程MD5，认为缓存有效

            is_valid = cached_md5 == remote_md5
            logger.debug(
                f"插件数据MD5: 本地={cached_md5}, 远程={remote_md5}, 有效={is_valid}",
            )
            return is_valid

        except Exception as e:
            logger.warning(f"检查缓存有效性失败: {e}")
            return False

    def _load_plugin_cache(self, cache_file: str):
        """加载本地缓存的插件市场数据"""
        try:
            if os.path.exists(cache_file):
                with open(cache_file, encoding="utf-8") as f:
                    cache_data = json.load(f)
                    # 检查缓存是否有效
                    if "data" in cache_data and "timestamp" in cache_data:
                        logger.debug(
                            f"加载缓存文件: {cache_file}, 缓存时间: {cache_data['timestamp']}",
                        )
                        return cache_data["data"]
        except Exception as e:
            logger.warning(f"加载插件市场缓存失败: {e}")
        return None

    def _save_plugin_cache(self, cache_file: str, data, md5: str | None = None) -> None:
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

    async def get_plugin_logo_token(self, logo_path: str):
        try:
            if token := self._logo_cache.get(logo_path):
                if not await file_token_service.check_token_expired(token):
                    return self._logo_cache[logo_path]
            token = await file_token_service.register_file(logo_path, timeout=300)
            self._logo_cache[logo_path] = token
            return token
        except Exception as e:
            logger.warning(f"获取插件 Logo 失败: {e}")
            return None

    async def get_plugins(self):
        _plugin_resp = []
        plugin_name = request.args.get("name")
        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin_name and plugin.name != plugin_name:
                continue
            logo_url = None
            if plugin.logo_path:
                logo_url = await self.get_plugin_logo_token(plugin.logo_path)
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
                    plugin.star_handler_full_names,
                ),
                "display_name": plugin.display_name,
                "logo": f"/api/file/{logo_url}" if logo_url else None,
            }
            # 检查是否为全空的幽灵插件
            if not any(
                [
                    plugin.name,
                    plugin.author,
                    plugin.desc,
                    plugin.version,
                    plugin.display_name,
                ]
            ):
                continue
            _plugin_resp.append(_t)
        return (
            Response()
            .ok(_plugin_resp, message=self.plugin_manager.failed_plugin_info)
            .__dict__
        )

    async def get_failed_plugins(self):
        """专门获取加载失败的插件列表(字典格式)"""
        return Response().ok(self.plugin_manager.failed_plugin_dict).__dict__

    async def get_plugin_handlers_info(self, handler_full_names: list[str]):
        """解析插件行为"""
        handlers = []

        for handler_full_name in handler_full_names:
            info = {}
            handler = star_handlers_registry.star_handlers_map.get(
                handler_full_name,
                None,
            )
            if handler is None:
                continue
            info["event_type"] = handler.event_type.name
            info["event_type_h"] = self.translated_event_type.get(
                handler.event_type,
                handler.event_type.name,
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
                            filter.sub_command_filters,
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

        post_data = await request.get_json()
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
            file_path = os.path.join(
                get_astrbot_temp_path(),
                f"plugin_upload_{file.filename}",
            )
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

        post_data = await request.get_json()
        plugin_name = post_data["name"]
        delete_config = post_data.get("delete_config", False)
        delete_data = post_data.get("delete_data", False)
        try:
            logger.info(f"正在卸载插件 {plugin_name}")
            await self.plugin_manager.uninstall_plugin(
                plugin_name,
                delete_config=delete_config,
                delete_data=delete_data,
            )
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

        post_data = await request.get_json()
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

    async def update_all_plugins(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.get_json()
        plugin_names: list[str] = post_data.get("names") or []
        proxy: str = post_data.get("proxy", "")

        if not isinstance(plugin_names, list) or not plugin_names:
            return Response().error("插件列表不能为空").__dict__

        results = []
        sem = asyncio.Semaphore(PLUGIN_UPDATE_CONCURRENCY)

        async def _update_one(name: str):
            async with sem:
                try:
                    logger.info(f"批量更新插件 {name}")
                    await self.plugin_manager.update_plugin(name, proxy)
                    return {"name": name, "status": "ok", "message": "更新成功"}
                except Exception as e:
                    logger.error(
                        f"/api/plugin/update-all: 更新插件 {name} 失败: {traceback.format_exc()}",
                    )
                    return {"name": name, "status": "error", "message": str(e)}

        raw_results = await asyncio.gather(
            *(_update_one(name) for name in plugin_names),
            return_exceptions=True,
        )
        for name, result in zip(plugin_names, raw_results):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                results.append(
                    {"name": name, "status": "error", "message": str(result)}
                )
            else:
                results.append(result)

        failed = [r for r in results if r["status"] == "error"]
        message = (
            "批量更新完成，全部成功。"
            if not failed
            else f"批量更新完成，其中 {len(failed)}/{len(results)} 个插件失败。"
        )

        return Response().ok({"results": results}, message).__dict__

    async def off_plugin(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.get_json()
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

        post_data = await request.get_json()
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

        if not plugin_obj.root_dir_name:
            logger.warning(f"插件 {plugin_name} 目录不存在")
            return Response().error(f"插件 {plugin_name} 目录不存在").__dict__

        plugin_dir = os.path.join(
            self.plugin_manager.plugin_store_path,
            plugin_obj.root_dir_name or "",
        )

        if not os.path.isdir(plugin_dir):
            logger.warning(f"无法找到插件目录: {plugin_dir}")
            return Response().error(f"无法找到插件 {plugin_name} 的目录").__dict__

        readme_path = os.path.join(plugin_dir, "README.md")

        if not os.path.isfile(readme_path):
            logger.warning(f"插件 {plugin_name} 没有README文件")
            return Response().error(f"插件 {plugin_name} 没有README文件").__dict__

        try:
            with open(readme_path, encoding="utf-8") as f:
                readme_content = f.read()

            return (
                Response()
                .ok({"content": readme_content}, "成功获取README内容")
                .__dict__
            )
        except Exception as e:
            logger.error(f"/api/plugin/readme: {traceback.format_exc()}")
            return Response().error(f"读取README文件失败: {e!s}").__dict__

    async def get_plugin_changelog(self):
        """获取插件更新日志

        读取插件目录下的 CHANGELOG.md 文件内容。
        """
        plugin_name = request.args.get("name")
        logger.debug(f"正在获取插件 {plugin_name} 的更新日志")

        if not plugin_name:
            return Response().error("插件名称不能为空").__dict__

        # 查找插件
        plugin_obj = None
        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin.name == plugin_name:
                plugin_obj = plugin
                break

        if not plugin_obj:
            return Response().error(f"插件 {plugin_name} 不存在").__dict__

        if not plugin_obj.root_dir_name:
            return Response().error(f"插件 {plugin_name} 目录不存在").__dict__

        plugin_dir = os.path.join(
            self.plugin_manager.plugin_store_path,
            plugin_obj.root_dir_name,
        )

        # 尝试多种可能的文件名
        changelog_names = ["CHANGELOG.md", "changelog.md", "CHANGELOG", "changelog"]
        for name in changelog_names:
            changelog_path = os.path.join(plugin_dir, name)
            if os.path.isfile(changelog_path):
                try:
                    with open(changelog_path, encoding="utf-8") as f:
                        changelog_content = f.read()
                    return (
                        Response()
                        .ok({"content": changelog_content}, "成功获取更新日志")
                        .__dict__
                    )
                except Exception as e:
                    logger.error(f"/api/plugin/changelog: {traceback.format_exc()}")
                    return Response().error(f"读取更新日志失败: {e!s}").__dict__

        # 没有找到 changelog 文件，返回 ok 但 content 为 null
        return Response().ok({"content": None}, "该插件没有更新日志文件").__dict__

    async def get_custom_source(self):
        """获取自定义插件源"""
        sources = await sp.global_get("custom_plugin_sources", [])
        return Response().ok(sources).__dict__

    async def save_custom_source(self):
        """保存自定义插件源"""
        try:
            data = await request.get_json()
            sources = data.get("sources", [])
            if not isinstance(sources, list):
                return Response().error("sources fields must be a list").__dict__

            await sp.global_put("custom_plugin_sources", sources)
            return Response().ok(None, "保存成功").__dict__
        except Exception as e:
            logger.error(f"/api/plugin/source/save: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__
