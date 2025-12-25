import asyncio
import traceback

from quart import request

from astrbot.core import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import (
    CONFIG_METADATA_2,
    CONFIG_METADATA_3,
    CONFIG_METADATA_3_SYSTEM,
    DEFAULT_CONFIG,
)
from astrbot.core.config.i18n_utils import ConfigMetadataI18n
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.platform.register import platform_registry
from astrbot.core.provider.register import provider_registry
from astrbot.core.star.star import star_registry

from ..services.platform import PlatformService
from ..services.provider import ProviderService
from ..services.utils import save_config
from .route import Response, Route, RouteContext


class ConfigRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.config: AstrBotConfig = core_lifecycle.astrbot_config
        self.acm = core_lifecycle.astrbot_config_mgr
        self.ucr = core_lifecycle.umop_config_router

        self.provider_service = ProviderService(core_lifecycle)
        self.platform_service = PlatformService(core_lifecycle)

        self.routes = {
            "/config/abconf/new": ("POST", self.create_abconf),
            "/config/abconf": ("GET", self.get_abconf),
            "/config/abconfs": ("GET", self.get_abconf_list),
            "/config/abconf/delete": ("POST", self.delete_abconf),
            "/config/abconf/update": ("POST", self.update_abconf),
            "/config/umo_abconf_routes": ("GET", self.get_uc_table),
            "/config/umo_abconf_route/update_all": ("POST", self.update_ucr_all),
            "/config/umo_abconf_route/update": ("POST", self.update_ucr),
            "/config/umo_abconf_route/delete": ("POST", self.delete_ucr),
            "/config/get": ("GET", self.get_configs),
            "/config/default": ("GET", self.get_default_config),
            "/config/astrbot/update": ("POST", self.post_astrbot_configs),
            "/config/plugin/update": ("POST", self.post_plugin_configs),
            "/config/platform/new": (
                "POST",
                self.platform_service.post_new_platform,
            ),
            "/config/platform/update": (
                "POST",
                self.platform_service.post_update_platform,
            ),
            "/config/platform/delete": (
                "POST",
                self.platform_service.post_delete_platform,
            ),
            "/config/platform/list": (
                "GET",
                self.platform_service.get_platform_list,
            ),
            # provider related
            "/config/provider/new": (
                "POST",
                self.provider_service.post_new_provider,
            ),
            "/config/provider/update": (
                "POST",
                self.provider_service.post_update_provider,
            ),
            "/config/provider/delete": (
                "POST",
                self.provider_service.post_delete_provider,
            ),
            "/config/provider/template": (
                "GET",
                self.provider_service.get_provider_template,
            ),
            "/config/provider/check_one": (
                "GET",
                self.provider_service.check_one_provider_status,
            ),
            "/config/provider/list": (
                "GET",
                self.provider_service.get_provider_config_list,
            ),
            "/config/provider/get_embedding_dim": (
                "POST",
                self.provider_service.get_embedding_dim,
            ),
            "/config/provider_sources/models": (
                "GET",
                self.provider_service.get_provider_source_models,
            ),
            "/config/provider_sources/update": (
                "POST",
                self.provider_service.update_provider_source,
            ),
            "/config/provider_sources/delete": (
                "POST",
                self.provider_service.delete_provider_source,
            ),
        }
        self.register_routes()

    async def get_uc_table(self):
        """获取 UMOP 配置路由表"""
        return Response().ok({"routing": self.ucr.umop_to_conf_id}).__dict__

    async def update_ucr_all(self):
        """更新 UMOP 配置路由表的全部内容"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").__dict__

        new_routing = post_data.get("routing", None)

        if not new_routing or not isinstance(new_routing, dict):
            return Response().error("缺少或错误的路由表数据").__dict__

        try:
            await self.ucr.update_routing_data(new_routing)
            return Response().ok(message="更新成功").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"更新路由表失败: {e!s}").__dict__

    async def update_ucr(self):
        """更新 UMOP 配置路由表"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").__dict__

        umo = post_data.get("umo", None)
        conf_id = post_data.get("conf_id", None)

        if not umo or not conf_id:
            return Response().error("缺少 UMO 或配置文件 ID").__dict__

        try:
            await self.ucr.update_route(umo, conf_id)
            return Response().ok(message="更新成功").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"更新路由表失败: {e!s}").__dict__

    async def delete_ucr(self):
        """删除 UMOP 配置路由表中的一项"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").__dict__

        umo = post_data.get("umo", None)

        if not umo:
            return Response().error("缺少 UMO").__dict__

        try:
            if umo in self.ucr.umop_to_conf_id:
                del self.ucr.umop_to_conf_id[umo]
                await self.ucr.update_routing_data(self.ucr.umop_to_conf_id)
            return Response().ok(message="删除成功").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"删除路由表项失败: {e!s}").__dict__

    async def get_default_config(self):
        """获取默认配置文件"""
        metadata = ConfigMetadataI18n.convert_to_i18n_keys(CONFIG_METADATA_3)
        return Response().ok({"config": DEFAULT_CONFIG, "metadata": metadata}).__dict__

    async def get_abconf_list(self):
        """获取所有 AstrBot 配置文件的列表"""
        abconf_list = self.acm.get_conf_list()
        return Response().ok({"info_list": abconf_list}).__dict__

    async def create_abconf(self):
        """创建新的 AstrBot 配置文件"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").__dict__
        name = post_data.get("name", None)
        config = post_data.get("config", DEFAULT_CONFIG)

        try:
            conf_id = self.acm.create_conf(name=name, config=config)
            return Response().ok(message="创建成功", data={"conf_id": conf_id}).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__

    async def get_abconf(self):
        """获取指定 AstrBot 配置文件"""
        abconf_id = request.args.get("id")
        system_config = request.args.get("system_config", "0").lower() == "1"
        if not abconf_id and not system_config:
            return Response().error("缺少配置文件 ID").__dict__

        try:
            if system_config:
                abconf = self.acm.confs["default"]
                metadata = ConfigMetadataI18n.convert_to_i18n_keys(
                    CONFIG_METADATA_3_SYSTEM
                )
                return Response().ok({"config": abconf, "metadata": metadata}).__dict__
            if abconf_id is None:
                raise ValueError("abconf_id cannot be None")
            abconf = self.acm.confs[abconf_id]
            metadata = ConfigMetadataI18n.convert_to_i18n_keys(CONFIG_METADATA_3)
            return Response().ok({"config": abconf, "metadata": metadata}).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__

    async def delete_abconf(self):
        """删除指定 AstrBot 配置文件"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").__dict__

        conf_id = post_data.get("id")
        if not conf_id:
            return Response().error("缺少配置文件 ID").__dict__

        try:
            success = self.acm.delete_conf(conf_id)
            if success:
                return Response().ok(message="删除成功").__dict__
            return Response().error("删除失败").__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"删除配置文件失败: {e!s}").__dict__

    async def update_abconf(self):
        """更新指定 AstrBot 配置文件信息"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").__dict__

        conf_id = post_data.get("id")
        if not conf_id:
            return Response().error("缺少配置文件 ID").__dict__

        name = post_data.get("name")

        try:
            success = self.acm.update_conf_info(conf_id, name=name)
            if success:
                return Response().ok(message="更新成功").__dict__
            return Response().error("更新失败").__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"更新配置文件失败: {e!s}").__dict__

    async def get_configs(self):
        # plugin_name 为空时返回 AstrBot 配置
        # 否则返回指定 plugin_name 的插件配置
        plugin_name = request.args.get("plugin_name", None)
        if not plugin_name:
            return Response().ok(await self._get_astrbot_config()).__dict__
        return Response().ok(await self._get_plugin_config(plugin_name)).__dict__

    async def post_astrbot_configs(self):
        data = await request.json
        config = data.get("config", None)
        conf_id = data.get("conf_id", None)

        try:
            # 不更新 provider_sources, provider, platform
            # 这些配置有单独的接口进行更新
            if conf_id == "default":
                no_update_keys = ["provider_sources", "provider", "platform"]
                for key in no_update_keys:
                    config[key] = self.acm.default_conf[key]

            await self._save_astrbot_configs(config, conf_id)
            await self.core_lifecycle.reload_pipeline_scheduler(conf_id)
            return Response().ok(None, "保存成功~").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def post_plugin_configs(self):
        post_configs = await request.json
        plugin_name = request.args.get("plugin_name", "unknown")
        try:
            await self._save_plugin_configs(post_configs, plugin_name)
            await self.core_lifecycle.plugin_manager.reload(plugin_name)
            return (
                Response()
                .ok(None, f"保存插件 {plugin_name} 成功~ 机器人正在热重载插件。")
                .__dict__
            )
        except Exception as e:
            return Response().error(str(e)).__dict__

    async def get_llm_tools(self):
        """获取函数调用工具。包含了本地加载的以及 MCP 服务的工具"""
        tool_mgr = self.core_lifecycle.provider_manager.llm_tools
        tools = tool_mgr.get_func_desc_openai_style()
        return Response().ok(tools).__dict__

    async def _get_astrbot_config(self):
        config = self.config

        # 平台适配器的默认配置模板注入
        platform_default_tmpl = CONFIG_METADATA_2["platform_group"]["metadata"][
            "platform"
        ]["config_template"]

        # 收集需要注册logo的平台
        logo_registration_tasks = []
        for platform in platform_registry:
            if platform.default_config_tmpl:
                platform_default_tmpl[platform.name] = platform.default_config_tmpl
                # 收集logo注册任务
                if platform.logo_path:
                    logo_registration_tasks.append(
                        self.platform_service.register_platform_logo(
                            platform, platform_default_tmpl
                        ),
                    )

        # 并行执行logo注册
        if logo_registration_tasks:
            await asyncio.gather(*logo_registration_tasks, return_exceptions=True)

        # 服务提供商的默认配置模板注入
        provider_default_tmpl = CONFIG_METADATA_2["provider_group"]["metadata"][
            "provider"
        ]["config_template"]
        for provider in provider_registry:
            if provider.default_config_tmpl:
                provider_default_tmpl[provider.type] = provider.default_config_tmpl

        return {"metadata": CONFIG_METADATA_2, "config": config}

    async def _get_plugin_config(self, plugin_name: str):
        ret: dict = {"metadata": None, "config": None}

        for plugin_md in star_registry:
            if plugin_md.name == plugin_name:
                if not plugin_md.config:
                    break
                ret["config"] = (
                    plugin_md.config
                )  # 这是自定义的 Dict 类（AstrBotConfig）
                ret["metadata"] = {
                    plugin_name: {
                        "description": f"{plugin_name} 配置",
                        "type": "object",
                        "items": plugin_md.config.schema,  # 初始化时通过 __setattr__ 存入了 schema
                    },
                }
                break

        return ret

    async def _save_astrbot_configs(
        self, post_configs: dict, conf_id: str | None = None
    ):
        try:
            if conf_id not in self.acm.confs:
                raise ValueError(f"配置文件 {conf_id} 不存在")
            astrbot_config = self.acm.confs[conf_id]

            # 保留服务端的 t2i_active_template 值
            if "t2i_active_template" in astrbot_config:
                post_configs["t2i_active_template"] = astrbot_config[
                    "t2i_active_template"
                ]

            save_config(post_configs, astrbot_config, is_core=True)
        except Exception as e:
            raise e

    async def _save_plugin_configs(self, post_configs: dict, plugin_name: str):
        md = None
        for plugin_md in star_registry:
            if plugin_md.name == plugin_name:
                md = plugin_md

        if not md:
            raise ValueError(f"插件 {plugin_name} 不存在")
        if not md.config:
            raise ValueError(f"插件 {plugin_name} 没有注册配置")

        try:
            save_config(post_configs, md.config)
        except Exception as e:
            raise e
