from __future__ import annotations

import asyncio
import hashlib
import json
import os
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
import certifi

from astrbot.api import sp
from astrbot.core import DEMO_MODE, file_token_service, logger
from astrbot.core.computer.computer_client import sync_skills_to_active_sandboxes
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from astrbot.core.star.star_manager import (
    PluginManager,
    PluginVersionUnsupportedError,
)
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_temp_path

PLUGIN_UPDATE_CONCURRENCY = 3
PLUGIN_OPERATION_FAILED_MESSAGE = "插件操作失败，请查看服务端日志。"
PLUGIN_UPDATE_FAILED_MESSAGE = "更新失败，请查看服务端日志。"
PLUGIN_COMPONENT_TYPE_ORDER = {
    "page": 0,
    "skill": 1,
    "command": 2,
    "llm_tool": 3,
    "listener": 4,
    "hook": 5,
}

LogoTokenResolver = Callable[[str], Awaitable[str | None]]
InstalledAtResolver = Callable[[StarMetadata], str | None]
PluginPagesResolver = Callable[[StarMetadata], Awaitable[list]]
PluginPagesSerializer = Callable[[StarMetadata], Awaitable[list[dict]]]


@dataclass
class RegistrySource:
    urls: list[str]
    cache_file: str
    md5_url: str | None


class PluginServiceError(Exception):
    def __init__(
        self,
        message: str,
        *,
        public_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.public_message = public_message or message


class PluginServiceWarning(Exception):
    def __init__(
        self,
        message: str,
        data: dict[str, Any],
        *,
        public_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.public_message = public_message or message
        self.data = data


class PluginService:
    def __init__(
        self,
        core_lifecycle,
        plugin_manager: PluginManager,
    ) -> None:
        self.core_lifecycle = core_lifecycle
        self.plugin_manager = plugin_manager
        self.translated_event_type = {
            EventType.AdapterMessageEvent: "平台消息下发时",
            EventType.OnLLMRequestEvent: "LLM 请求时",
            EventType.OnLLMResponseEvent: "LLM 响应后",
            EventType.OnAgentBeginEvent: "Agent 开始运行时",
            EventType.OnAgentDoneEvent: "Agent 运行完成后",
            EventType.OnDecoratingResultEvent: "回复消息前",
            EventType.OnCallingFuncToolEvent: "函数工具",
            EventType.OnAfterMessageSentEvent: "发送消息后",
            EventType.OnPluginErrorEvent: "插件报错时",
        }
        self._logo_cache: dict[str, str] = {}

    @staticmethod
    def _payload(data: object) -> dict[str, Any]:
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _ensure_not_demo() -> None:
        if DEMO_MODE:
            raise PluginServiceError(
                "You are not permitted to do this operation in demo mode"
            )

    async def sync_skills_after_plugin_change(self) -> None:
        try:
            await sync_skills_to_active_sandboxes()
        except Exception:
            logger.warning("Failed to sync plugin-provided skills to active sandboxes.")

    async def check_plugin_version_support(self, data: object) -> dict:
        payload = self._payload(data)
        version_spec = payload.get("astrbot_version", "")
        is_valid, message = self.plugin_manager._validate_astrbot_version_specifier(
            version_spec
        )
        return {
            "supported": is_valid,
            "message": message,
            "astrbot_version": version_spec,
        }

    async def reload_failed_plugin(self, data: object) -> tuple[None, str]:
        self._ensure_not_demo()
        payload = data if isinstance(data, dict) else {}
        dir_name = payload.get("dir_name")
        if not dir_name:
            raise PluginServiceError("缺少插件目录名")

        success, err = await self.plugin_manager.reload_failed_plugin(dir_name)
        if not success:
            raise PluginServiceError(f"重载失败: {err}", public_message="重载失败")
        await self.sync_skills_after_plugin_change()
        return None, f"插件 {dir_name} 重载成功。"

    async def reload_plugin(self, data: object) -> tuple[None, str]:
        self._ensure_not_demo()
        payload = data if isinstance(data, dict) else {}
        plugin_name = payload.get("name", None)
        success, message = await self.plugin_manager.reload(plugin_name)
        if not success:
            raise PluginServiceError(
                message or "插件重载失败",
                public_message="插件重载失败",
            )
        await self.sync_skills_after_plugin_change()
        return None, "重载成功。"

    async def list_plugins(
        self,
        *,
        plugin_name: str | None,
        logo_token_resolver: LogoTokenResolver,
        installed_at_resolver: InstalledAtResolver,
        discover_pages: PluginPagesResolver,
    ) -> tuple[list[dict], str | None]:
        plugins = [
            plugin
            for plugin in self.plugin_manager.context.get_all_stars()
            if not (plugin_name and plugin.name != plugin_name)
        ]

        async def process_plugin(plugin: StarMetadata):
            logo_url = await self.resolve_plugin_logo_url(plugin, logo_token_resolver)
            pages = await discover_pages(plugin)
            return plugin, logo_url, pages

        results = await asyncio.gather(*(process_plugin(plugin) for plugin in plugins))
        payload = []
        for plugin, logo_url, pages in results:
            if self.is_ghost_plugin(plugin):
                continue
            payload.append(
                {
                    **self.serialize_plugin_base(
                        plugin,
                        logo_url=logo_url,
                        installed_at=installed_at_resolver(plugin),
                    ),
                    "pages": [page.name for page in pages],
                }
            )
        return payload, getattr(self.plugin_manager, "failed_plugin_info", None)

    async def list_plugins_from_dashboard_query(
        self,
        *,
        plugin_name: str | None,
        logo_token_resolver: LogoTokenResolver,
        installed_at_resolver: InstalledAtResolver,
        discover_pages: PluginPagesResolver,
    ) -> tuple[list[dict], str | None]:
        return await self.list_plugins(
            plugin_name=plugin_name,
            logo_token_resolver=logo_token_resolver,
            installed_at_resolver=installed_at_resolver,
            discover_pages=discover_pages,
        )

    async def get_plugin_detail(
        self,
        *,
        plugin_name: str | None,
        logo_token_resolver: LogoTokenResolver,
        installed_at_resolver: InstalledAtResolver,
        serialize_pages: PluginPagesSerializer,
    ) -> dict:
        if not plugin_name:
            raise PluginServiceError("缺少插件名")

        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin.name != plugin_name:
                continue

            logo_url = await self.resolve_plugin_logo_url(plugin, logo_token_resolver)
            return {
                **self.serialize_plugin_base(
                    plugin,
                    logo_url=logo_url,
                    installed_at=installed_at_resolver(plugin),
                ),
                "components": await self.get_plugin_components_info(
                    plugin,
                    serialize_pages,
                ),
            }

        raise PluginServiceError("插件不存在")

    async def get_plugin_detail_from_dashboard_query(
        self,
        *,
        plugin_name: str | None,
        logo_token_resolver: LogoTokenResolver,
        installed_at_resolver: InstalledAtResolver,
        serialize_pages: PluginPagesSerializer,
    ) -> dict:
        return await self.get_plugin_detail(
            plugin_name=plugin_name,
            logo_token_resolver=logo_token_resolver,
            installed_at_resolver=installed_at_resolver,
            serialize_pages=serialize_pages,
        )

    async def resolve_plugin_logo_url(
        self,
        plugin: StarMetadata,
        logo_token_resolver: LogoTokenResolver,
    ) -> str | None:
        if not plugin.logo_path:
            return None
        logo_token = await logo_token_resolver(plugin.logo_path)
        return f"/api/file/{logo_token}" if logo_token else None

    async def get_plugin_logo_token(self, logo_path: str) -> str | None:
        try:
            if token := self._logo_cache.get(logo_path):
                if not await file_token_service.check_token_expired(token):
                    return token
            token = await file_token_service.register_file(logo_path, timeout=300)
            self._logo_cache[logo_path] = token
            return token
        except Exception as exc:
            logger.warning(f"获取插件 Logo 失败: {exc}")
            return None

    def resolve_plugin_metadata_dir(self, plugin: StarMetadata) -> Path | None:
        if not plugin.root_dir_name:
            return None

        base_dir = Path(
            self.plugin_manager.reserved_plugin_path
            if plugin.reserved
            else self.plugin_manager.plugin_store_path
        )
        plugin_dir = base_dir / plugin.root_dir_name
        if not plugin_dir.is_dir():
            return None
        return plugin_dir

    def get_plugin_installed_at(self, plugin: StarMetadata) -> str | None:
        plugin_dir = self.resolve_plugin_metadata_dir(plugin)
        if plugin_dir is None:
            return None

        try:
            return datetime.fromtimestamp(
                plugin_dir.stat().st_mtime,
                timezone.utc,
            ).isoformat()
        except OSError as exc:
            logger.warning(f"获取插件安装时间失败 {plugin.name}: {exc!s}")
            return None

    @staticmethod
    def is_ghost_plugin(plugin: StarMetadata) -> bool:
        return not any(
            [
                plugin.name,
                plugin.author,
                plugin.desc,
                plugin.version,
                plugin.display_name,
            ]
        )

    @staticmethod
    def serialize_plugin_base(
        plugin: StarMetadata,
        *,
        logo_url: str | None,
        installed_at: str | None,
    ) -> dict:
        return {
            "name": plugin.name,
            "marketplace_name": (plugin.name or "").replace("_", "-"),
            "repo": "" if plugin.repo is None else str(plugin.repo),
            "author": plugin.author,
            "desc": plugin.desc,
            "version": plugin.version,
            "reserved": plugin.reserved,
            "activated": plugin.activated,
            "online_vesion": "",
            "display_name": plugin.display_name,
            "logo": logo_url,
            "support_platforms": plugin.support_platforms,
            "astrbot_version": plugin.astrbot_version,
            "installed_at": installed_at,
            "i18n": plugin.i18n,
        }

    def get_failed_plugins(self) -> dict:
        return self.plugin_manager.failed_plugin_dict

    async def get_plugin_components_info(
        self,
        plugin: StarMetadata,
        serialize_pages: PluginPagesSerializer,
    ) -> list[dict]:
        components = [
            *await self.get_plugin_page_components(plugin, serialize_pages),
            *self.get_plugin_skill_components(plugin),
            *await self.get_plugin_handler_components(plugin.star_handler_full_names),
        ]
        return sorted(
            components,
            key=lambda item: PLUGIN_COMPONENT_TYPE_ORDER.get(item["type"], 99),
        )

    async def get_plugin_page_components(
        self,
        plugin: StarMetadata,
        serialize_pages: PluginPagesSerializer,
    ) -> list[dict]:
        pages = await serialize_pages(plugin)
        return [
            {
                "type": "page",
                "name": page["title"],
                "title": page["title"],
                "page_name": page["name"],
                "i18n_key": page["i18n_key"],
                "description": "Plugin Page entry",
                "plugin_name": plugin.name,
                "plugin_marketplace_name": (plugin.name or "").replace("_", "-"),
            }
            for page in pages
        ]

    async def get_plugin_handler_components(
        self,
        handler_full_names: list[str],
    ) -> list[dict]:
        components = []

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
            info["description"] = handler.desc or "无描述"
            info["handler_name"] = handler.handler_name

            component_type = "hook"
            component: dict[str, Any] | None = None
            if handler.event_type == EventType.AdapterMessageEvent:
                has_admin = False
                for event_filter in handler.event_filters:
                    if isinstance(event_filter, CommandFilter):
                        component_type = "command"
                        info["display_type"] = "指令"
                        info["cmd"] = self._get_command_filter_display_name(
                            event_filter
                        )
                        component = self._build_command_filter_component(
                            event_filter,
                            handler.desc,
                        )
                    elif isinstance(event_filter, CommandGroupFilter):
                        component_type = "command"
                        info["display_type"] = "指令组"
                        info["cmd"] = event_filter.get_complete_command_names()[
                            0
                        ].strip()
                        component = self._build_command_group_component(
                            event_filter,
                            handler.desc,
                        )
                    elif isinstance(event_filter, RegexFilter):
                        component_type = "command"
                        info["display_type"] = "正则匹配"
                        info["cmd"] = event_filter.regex_str
                        component = {
                            "type": "command",
                            "name": event_filter.regex_str,
                            "description": handler.desc or "无描述",
                            "match": "regex",
                        }
                    elif isinstance(event_filter, PermissionTypeFilter):
                        has_admin = True
                info["has_admin"] = has_admin
                if "cmd" not in info:
                    info["cmd"] = "未知"
                if "display_type" not in info:
                    info["display_type"] = "事件监听器"
                    component_type = "listener"
            else:
                info["cmd"] = "自动触发"
                info["display_type"] = "无"
                if handler.event_type == EventType.OnCallingFuncToolEvent:
                    component_type = "llm_tool"

            if component is None:
                component = {
                    "type": component_type,
                    "name": handler.handler_name or handler.event_type.name,
                    "description": handler.desc or "无描述",
                }
            else:
                component["type"] = component_type

            if component_type == "command":
                component["event_type"] = info["event_type"]
                component["event_type_h"] = info["event_type_h"]
                component["handler_name"] = info["handler_name"]
                component["has_admin"] = info.get("has_admin", False)
                if "display_type" in info:
                    component["display_type"] = info["display_type"]
                if "cmd" in info:
                    component["command"] = info["cmd"]
            else:
                component.update(info)
            components.append(component)

        return self._merge_command_components(components)

    def get_plugin_skill_components(self, plugin: StarMetadata) -> list[dict]:
        plugin_names = {
            str(name)
            for name in (plugin.root_dir_name, plugin.name)
            if str(name or "").strip()
        }
        if not plugin_names:
            return []

        try:
            skills = SkillManager().list_skills(
                active_only=False,
                runtime="local",
                show_sandbox_path=False,
            )
        except Exception as exc:
            logger.warning(f"获取插件 Skills 失败 {plugin.name}: {exc!s}")
            return []

        components = []
        for skill in skills:
            if skill.source_type != "plugin" or skill.plugin_name not in plugin_names:
                continue
            components.append(
                {
                    "type": "skill",
                    "name": skill.name,
                    "description": skill.description or "无描述",
                    "path": skill.path,
                }
            )
        return components

    @staticmethod
    def _get_command_filter_display_name(command_filter: CommandFilter) -> str:
        return command_filter.get_complete_command_names()[0].strip()

    @staticmethod
    def _get_command_description(
        command_filter: CommandFilter | CommandGroupFilter,
        fallback: str = "",
    ) -> str:
        handler_md = getattr(command_filter, "handler_md", None)
        desc = getattr(handler_md, "desc", "") if handler_md else ""
        return desc or fallback or "无描述"

    def _build_command_filter_component(
        self,
        command_filter: CommandFilter,
        fallback_desc: str = "",
    ) -> dict:
        parts = self._get_command_filter_display_name(command_filter).split()
        if not parts:
            parts = [command_filter.command_name]
        component: dict[str, Any] = {
            "type": "command",
            "name": parts[-1],
            "description": self._get_command_description(
                command_filter,
                fallback_desc,
            ),
        }
        return self._wrap_command_component(parts[:-1], component)

    def _build_command_group_component(
        self,
        command_group_filter: CommandGroupFilter,
        fallback_desc: str = "",
    ) -> dict:
        parts = command_group_filter.get_complete_command_names()[0].strip().split()
        if not parts:
            parts = [command_group_filter.group_name]
        subcommands = [
            self._build_command_group_child(sub_filter)
            for sub_filter in command_group_filter.sub_command_filters
        ]
        component: dict[str, Any] = {
            "type": "command",
            "name": parts[-1],
            "description": self._get_command_description(
                command_group_filter,
                fallback_desc,
            ),
        }
        if subcommands:
            component["subcommands"] = subcommands
        return self._wrap_command_component(parts[:-1], component)

    def _build_command_group_child(
        self,
        command_filter: CommandFilter | CommandGroupFilter,
    ) -> dict:
        if isinstance(command_filter, CommandGroupFilter):
            component: dict[str, Any] = {
                "name": command_filter.group_name,
                "description": self._get_command_description(command_filter),
            }
            subcommands = [
                self._build_command_group_child(sub_filter)
                for sub_filter in command_filter.sub_command_filters
            ]
            if subcommands:
                component["subcommands"] = subcommands
            return component

        return {
            "name": command_filter.command_name,
            "description": self._get_command_description(command_filter),
        }

    @staticmethod
    def _wrap_command_component(parent_names: list[str], component: dict) -> dict:
        for parent_name in reversed(parent_names):
            component = {
                "type": "command",
                "name": parent_name,
                "description": "无描述",
                "subcommands": [component],
            }
        return component

    def _merge_command_components(self, components: list[dict]) -> list[dict]:
        merged: list[dict] = []
        for component in components:
            if component.get("type") != "command":
                merged.append(component)
                continue
            existing = next(
                (
                    item
                    for item in merged
                    if item.get("type") == "command"
                    and item.get("name") == component.get("name")
                    and item.get("match") == component.get("match")
                ),
                None,
            )
            if existing is None:
                merged.append(component)
                continue
            self._merge_command_component(existing, component)
        return merged

    def _merge_command_component(self, target: dict, source: dict) -> None:
        if target.get("description") == "无描述" and source.get("description"):
            target["description"] = source["description"]
        for key, value in source.items():
            if key in {"subcommands", "description"}:
                continue
            target.setdefault(key, value)

        source_subcommands = source.get("subcommands")
        if not isinstance(source_subcommands, list):
            return
        target_subcommands = target.setdefault("subcommands", [])
        for source_subcommand in source_subcommands:
            if not isinstance(source_subcommand, dict):
                continue
            existing = next(
                (
                    item
                    for item in target_subcommands
                    if isinstance(item, dict)
                    and item.get("name") == source_subcommand.get("name")
                ),
                None,
            )
            if existing is None:
                target_subcommands.append(source_subcommand)
                continue
            self._merge_command_component(existing, source_subcommand)

    async def get_online_plugins(
        self,
        *,
        custom_registry: str | None,
        force_refresh: bool,
    ) -> tuple[Any, str | None]:
        source = self.build_registry_source(custom_registry)

        cached_data = None
        if not force_refresh and await self.is_cache_valid(source):
            cached_data = self.load_plugin_cache(source.cache_file)
            if cached_data:
                logger.debug("缓存MD5匹配，使用缓存的插件市场数据")
                return cached_data, None

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

                        if not remote_data or (
                            isinstance(remote_data, dict) and len(remote_data) == 0
                        ):
                            logger.warning(f"远程插件市场数据为空: {url}")
                            continue

                        logger.info(
                            f"成功获取远程插件市场数据，包含 {len(remote_data)} 个插件"
                        )
                        current_md5 = await self.fetch_remote_md5(source.md5_url)
                        self.save_plugin_cache(
                            source.cache_file,
                            remote_data,
                            current_md5,
                        )
                        return remote_data, None
                    logger.error(f"请求 {url} 失败，状态码：{response.status}")
            except Exception as exc:
                logger.error(f"请求 {url} 失败，错误：{exc}")

        if not cached_data:
            cached_data = self.load_plugin_cache(source.cache_file)

        if cached_data:
            logger.warning("远程插件市场数据获取失败，使用缓存数据")
            return cached_data, "使用缓存数据，可能不是最新版本"

        raise PluginServiceError("获取插件列表失败，且没有可用的缓存数据")

    async def get_online_plugins_from_dashboard_query(
        self,
        *,
        custom_registry: str | None,
        force_refresh,
    ) -> tuple[Any, str | None]:
        return await self.get_online_plugins(
            custom_registry=custom_registry,
            force_refresh=self._to_bool(force_refresh),
        )

    @staticmethod
    def build_registry_source(custom_url: str | None) -> RegistrySource:
        data_dir = get_astrbot_data_path()
        if custom_url:
            url_hash = hashlib.md5(custom_url.encode()).hexdigest()[:8]
            cache_file = os.path.join(data_dir, f"plugins_custom_{url_hash}.json")
            md5_url = (
                custom_url[:-5] + "-md5.json"
                if custom_url.endswith(".json")
                else custom_url + "-md5.json"
            )
            urls = [custom_url]
        else:
            cache_file = os.path.join(data_dir, "plugins.json")
            md5_url = "https://api.soulter.top/astrbot/plugins-md5"
            urls = [
                "https://api.soulter.top/astrbot/plugins",
                "https://github.com/AstrBotDevs/AstrBot_Plugins_Collection/raw/refs/heads/main/plugin_cache_original.json",
            ]
        return RegistrySource(urls=urls, cache_file=cache_file, md5_url=md5_url)

    @staticmethod
    def load_cached_md5(cache_file: str) -> str | None:
        if not os.path.exists(cache_file):
            return None

        try:
            with open(cache_file, encoding="utf-8") as file:
                cache_data = json.load(file)
            return cache_data.get("md5")
        except Exception as exc:
            logger.warning(f"Failed to load cached MD5: {exc}")
            return None

    @staticmethod
    async def fetch_remote_md5(md5_url: str | None) -> str | None:
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
        except Exception as exc:
            logger.debug(f"Failed to fetch remote MD5: {exc}")
        return None

    async def is_cache_valid(self, source: RegistrySource) -> bool:
        try:
            cached_md5 = self.load_cached_md5(source.cache_file)
            if not cached_md5:
                logger.debug("MD5 not found in cache, treating cache as invalid")
                return False

            remote_md5 = await self.fetch_remote_md5(source.md5_url)
            if remote_md5 is None:
                logger.warning(
                    "Cannot fetch remote MD5, using cache without validation"
                )
                return True

            is_valid = cached_md5 == remote_md5
            logger.debug(
                f"Plugin cache: local={cached_md5}, remote={remote_md5}, effective={is_valid}",
            )
            return is_valid

        except Exception as exc:
            logger.warning(f"检查缓存有效性失败: {exc}")
            return False

    @staticmethod
    def load_plugin_cache(cache_file: str):
        try:
            if os.path.exists(cache_file):
                with open(cache_file, encoding="utf-8") as file:
                    cache_data = json.load(file)
                    if "data" in cache_data and "timestamp" in cache_data:
                        logger.debug(
                            f"Loading cached file: {cache_file}, Cache time: {cache_data['timestamp']}",
                        )
                        return cache_data["data"]
        except Exception as exc:
            logger.warning(f"Failed to load plugin market cache: {exc}")
        return None

    @staticmethod
    def save_plugin_cache(cache_file: str, data, md5: str | None = None) -> None:
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)

            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "data": data,
                "md5": md5 or "",
            }

            with open(cache_file, "w", encoding="utf-8") as file:
                json.dump(cache_data, file, ensure_ascii=False, indent=2)
            logger.debug(f"Cached plugin market data: {cache_file}, MD5: {md5}")
        except Exception as exc:
            logger.warning(f"Failed to save plugin market cache: {exc}")

    async def install_plugin(self, data: object) -> tuple[dict, str]:
        self._ensure_not_demo()
        payload = data if isinstance(data, dict) else {}
        repo_url = payload["url"]
        download_url = str(payload.get("download_url") or "").strip()
        ignore_version_check = bool(payload.get("ignore_version_check", False))

        proxy: str | None = payload.get("proxy", None)
        if proxy:
            proxy = proxy.removesuffix("/")

        try:
            logger.info(f"正在安装插件 {repo_url}")
            plugin_info = await self.plugin_manager.install_plugin(
                repo_url,
                proxy or "",
                ignore_version_check=ignore_version_check,
                download_url=download_url,
            )
            await self.sync_skills_after_plugin_change()
            logger.info(f"安装插件 {repo_url} 成功。")
            return plugin_info or {}, "安装成功。"
        except PluginVersionUnsupportedError as exc:
            raise PluginServiceWarning(
                str(exc),
                {
                    "warning_type": "astrbot_version_unsupported",
                    "can_ignore": True,
                },
                public_message="当前 AstrBot 版本不满足插件要求",
            ) from exc

    async def install_plugin_upload(
        self,
        *,
        upload_file,
        ignore_version_check: bool,
    ) -> tuple[dict, str]:
        self._ensure_not_demo()
        logger.info(f"正在安装用户上传的插件 {upload_file.filename}")
        file_path = os.path.join(
            get_astrbot_temp_path(),
            f"plugin_upload_{upload_file.filename}",
        )
        await upload_file.save(file_path)
        try:
            plugin_info = await self.plugin_manager.install_plugin_from_file(
                file_path,
                ignore_version_check=ignore_version_check,
            )
            await self.sync_skills_after_plugin_change()
            logger.info(f"安装插件 {upload_file.filename} 成功")
            return plugin_info or {}, "安装成功。"
        except PluginVersionUnsupportedError as exc:
            raise PluginServiceWarning(
                str(exc),
                {
                    "warning_type": "astrbot_version_unsupported",
                    "can_ignore": True,
                },
                public_message="当前 AstrBot 版本不满足插件要求",
            ) from exc

    async def install_plugin_upload_from_dashboard_form(
        self,
        *,
        upload_file,
        ignore_version_check,
    ) -> tuple[dict, str]:
        return await self.install_plugin_upload(
            upload_file=upload_file,
            ignore_version_check=self._to_bool(ignore_version_check),
        )

    async def uninstall_plugin(self, data: object) -> tuple[None, str]:
        self._ensure_not_demo()
        payload = data if isinstance(data, dict) else {}
        plugin_name = payload["name"]
        delete_config = payload.get("delete_config", False)
        delete_data = payload.get("delete_data", False)
        logger.info(f"正在卸载插件 {plugin_name}")
        await self.plugin_manager.uninstall_plugin(
            plugin_name,
            delete_config=delete_config,
            delete_data=delete_data,
        )
        await self.sync_skills_after_plugin_change()
        logger.info(f"卸载插件 {plugin_name} 成功")
        return None, "卸载成功"

    async def uninstall_failed_plugin(self, data: object) -> tuple[None, str]:
        self._ensure_not_demo()
        payload = data if isinstance(data, dict) else {}
        dir_name = payload.get("dir_name", "")
        delete_config = payload.get("delete_config", False)
        delete_data = payload.get("delete_data", False)
        if not dir_name:
            raise PluginServiceError("缺少失败插件目录名")

        logger.info(f"正在卸载失败插件 {dir_name}")
        await self.plugin_manager.uninstall_failed_plugin(
            dir_name,
            delete_config=delete_config,
            delete_data=delete_data,
        )
        await self.sync_skills_after_plugin_change()
        logger.info(f"卸载失败插件 {dir_name} 成功")
        return None, "卸载成功"

    async def update_plugin(self, data: object) -> tuple[None, str]:
        self._ensure_not_demo()
        payload = data if isinstance(data, dict) else {}
        plugin_name = payload["name"]
        proxy: str | None = payload.get("proxy", None)
        download_url = str(payload.get("download_url") or "").strip()
        logger.info(f"正在更新插件 {plugin_name}")
        await self.plugin_manager.update_plugin(
            plugin_name, proxy or "", download_url=download_url
        )
        await self.plugin_manager.reload(plugin_name)
        await self.sync_skills_after_plugin_change()
        logger.info(f"更新插件 {plugin_name} 成功。")
        return None, "更新成功。"

    async def update_all_plugins(self, data: object) -> tuple[dict, str]:
        self._ensure_not_demo()
        payload = data if isinstance(data, dict) else {}
        plugin_names: list[str] = payload.get("names") or []
        proxy: str = payload.get("proxy", "")
        download_urls: dict[str, str] = payload.get("download_urls") or {}

        if not isinstance(plugin_names, list) or not plugin_names:
            raise PluginServiceError("插件列表不能为空")
        if not isinstance(download_urls, dict):
            download_urls = {}

        results = []
        sem = asyncio.Semaphore(PLUGIN_UPDATE_CONCURRENCY)

        async def _update_one(name: str):
            async with sem:
                try:
                    logger.info(f"批量更新插件 {name}")
                    download_url = str(download_urls.get(name) or "").strip()
                    await self.plugin_manager.update_plugin(
                        name, proxy, download_url=download_url
                    )
                    return {"name": name, "status": "ok", "message": "更新成功"}
                except Exception:
                    logger.error(
                        f"/api/plugin/update-all: 更新插件 {name} 失败",
                        exc_info=True,
                    )
                    return {
                        "name": name,
                        "status": "error",
                        "message": PLUGIN_UPDATE_FAILED_MESSAGE,
                    }

        raw_results = await asyncio.gather(
            *(_update_one(name) for name in plugin_names),
            return_exceptions=True,
        )
        for name, result in zip(plugin_names, raw_results):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                logger.error(
                    f"/api/plugin/update-all: 更新插件 {name} 任务失败: {result!r}"
                )
                results.append(
                    {
                        "name": name,
                        "status": "error",
                        "message": PLUGIN_UPDATE_FAILED_MESSAGE,
                    }
                )
            else:
                results.append(result)

        failed = [result for result in results if result["status"] == "error"]
        if len(failed) < len(results):
            await self.sync_skills_after_plugin_change()
        message = (
            "批量更新完成，全部成功。"
            if not failed
            else f"批量更新完成，其中 {len(failed)}/{len(results)} 个插件失败。"
        )

        return {"results": results}, message

    async def set_plugin_enabled(
        self, data: object, *, enabled: bool
    ) -> tuple[None, str]:
        self._ensure_not_demo()
        payload = data if isinstance(data, dict) else {}
        plugin_name = payload["name"]
        if enabled:
            await self.plugin_manager.turn_on_plugin(plugin_name)
            message = "启用成功。"
            log_action = "启用"
        else:
            await self.plugin_manager.turn_off_plugin(plugin_name)
            message = "停用成功。"
            log_action = "停用"
        await self.sync_skills_after_plugin_change()
        logger.info(f"{log_action}插件 {plugin_name} 。")
        return None, message

    def resolve_plugin_dir(self, plugin_name: str) -> Path:
        if not plugin_name:
            raise PluginServiceError("插件名称不能为空")

        plugin_obj = None
        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin.name == plugin_name:
                plugin_obj = plugin
                break

        if not plugin_obj:
            raise PluginServiceError(f"插件 {plugin_name} 不存在")
        if not plugin_obj.root_dir_name:
            raise PluginServiceError(f"插件 {plugin_name} 目录不存在")

        plugin_dir = (
            Path(
                self.plugin_manager.reserved_plugin_path
                if plugin_obj.reserved
                else self.plugin_manager.plugin_store_path
            )
            / plugin_obj.root_dir_name
        )
        if not plugin_dir.is_dir():
            raise PluginServiceError(f"无法找到插件 {plugin_name} 的目录")
        return plugin_dir

    def get_plugin_readme(self, plugin_name: str | None) -> tuple[dict, str]:
        if not plugin_name:
            logger.warning("插件名称为空")
            raise PluginServiceError("插件名称不能为空")

        plugin_dir = self.resolve_plugin_dir(plugin_name)
        readme_path = plugin_dir / "README.md"

        if not readme_path.is_file():
            logger.warning(f"插件 {plugin_name} 没有README文件")
            raise PluginServiceError(f"插件 {plugin_name} 没有README文件")

        try:
            return {
                "content": readme_path.read_text(encoding="utf-8")
            }, "成功获取README内容"
        except Exception as exc:
            logger.warning(f"读取插件 {plugin_name} README 文件失败: {exc}")
            raise PluginServiceError(
                "读取README文件失败",
                public_message="读取README文件失败",
            ) from exc

    def get_plugin_readme_from_dashboard_query(
        self,
        plugin_name: str | None,
    ) -> tuple[dict, str]:
        return self.get_plugin_readme(plugin_name)

    def get_plugin_changelog(self, plugin_name: str | None) -> tuple[dict, str]:
        logger.debug(f"正在获取插件 {plugin_name} 的更新日志")
        if not plugin_name:
            logger.warning("插件名称为空")
            raise PluginServiceError("插件名称不能为空")

        plugin_dir = self.resolve_plugin_dir(plugin_name)
        changelog_names = ["CHANGELOG.md", "changelog.md", "CHANGELOG", "changelog"]
        for name in changelog_names:
            changelog_path = plugin_dir / name
            if not changelog_path.is_file():
                continue
            try:
                return (
                    {"content": changelog_path.read_text(encoding="utf-8")},
                    "成功获取更新日志",
                )
            except Exception as exc:
                logger.warning(f"读取插件 {plugin_name} 更新日志失败: {exc}")
                raise PluginServiceError(
                    "读取更新日志失败",
                    public_message="读取更新日志失败",
                ) from exc

        logger.warning(f"插件 {plugin_name} 没有更新日志文件")
        return {"content": None}, "该插件没有更新日志文件"

    def get_plugin_changelog_from_dashboard_query(
        self,
        plugin_name: str | None,
    ) -> tuple[dict, str]:
        return self.get_plugin_changelog(plugin_name)

    @staticmethod
    async def get_custom_sources() -> list:
        return PluginService._normalize_custom_sources(
            await sp.global_get("custom_plugin_sources", [])
        )

    @staticmethod
    async def save_custom_sources(data: object) -> tuple[None, str]:
        payload = data if isinstance(data, dict) else {}
        sources = PluginService._custom_sources_from_payload(payload)
        await sp.global_put("custom_plugin_sources", sources)
        return None, "保存成功"

    @staticmethod
    def _normalize_custom_sources(raw_sources: object) -> list:
        return raw_sources if isinstance(raw_sources, list) else []

    @staticmethod
    def _custom_sources_from_payload(payload: dict[str, Any]) -> list:
        sources = payload.get("sources", [])
        if not isinstance(sources, list):
            raise PluginServiceError("sources fields must be a list")
        return sources

    @staticmethod
    async def create_custom_source(data: object) -> list:
        source = data if isinstance(data, dict) else {}
        sources = await PluginService.get_custom_sources()
        sources.append(source)
        await sp.global_put("custom_plugin_sources", sources)
        return sources

    @staticmethod
    async def replace_custom_sources(data: object) -> list:
        payload = data if isinstance(data, dict) else {}
        sources = PluginService._custom_sources_from_payload(payload)
        await sp.global_put("custom_plugin_sources", sources)
        return sources

    @staticmethod
    async def delete_custom_source(source_id: str) -> list:
        sources = await PluginService.get_custom_sources()
        filtered = [
            source
            for source in sources
            if not (
                isinstance(source, dict)
                and str(source.get("id") or source.get("url") or source.get("name"))
                == source_id
            )
            and not (isinstance(source, str) and source == source_id)
        ]
        await sp.global_put("custom_plugin_sources", filtered)
        return filtered

    @staticmethod
    def _to_bool(value: object, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)


__all__ = [
    "PLUGIN_UPDATE_CONCURRENCY",
    "PLUGIN_OPERATION_FAILED_MESSAGE",
    "PLUGIN_UPDATE_FAILED_MESSAGE",
    "PluginService",
    "PluginServiceError",
    "PluginServiceWarning",
    "RegistrySource",
]
