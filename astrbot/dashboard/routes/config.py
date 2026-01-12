import asyncio
import inspect
import os
import traceback
from typing import Any

from quart import request

from astrbot.core import astrbot_config, file_token_service, logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import (
    CONFIG_METADATA_2,
    CONFIG_METADATA_3,
    CONFIG_METADATA_3_SYSTEM,
    DEFAULT_CONFIG,
    DEFAULT_VALUE_MAP,
)
from astrbot.core.config.i18n_utils import ConfigMetadataI18n
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.platform.register import platform_cls_map, platform_registry
from astrbot.core.provider import Provider
from astrbot.core.provider.register import provider_registry
from astrbot.core.star.star import star_registry
from astrbot.core.utils.llm_metadata import LLM_METADATAS
from astrbot.core.utils.webhook_utils import ensure_platform_webhook_config

from .route import Response, Route, RouteContext


def try_cast(value: Any, type_: str):
    if type_ == "int":
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    elif (
        type_ == "float"
        and isinstance(value, str)
        and value.replace(".", "", 1).isdigit()
    ) or (type_ == "float" and isinstance(value, int)):
        return float(value)
    elif type_ == "float":
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


def _expect_type(value, expected_type, path_key, errors, expected_name=None):
    if not isinstance(value, expected_type):
        errors.append(
            f"错误的类型 {path_key}: 期望是 {expected_name or expected_type.__name__}, "
            f"得到了 {type(value).__name__}"
        )
        return False
    return True


def _validate_template_list(value, meta, path_key, errors, validate_fn):
    if not _expect_type(value, list, path_key, errors, "list"):
        return

    templates = meta.get("templates")
    if not isinstance(templates, dict):
        templates = {}

    for idx, item in enumerate(value):
        item_path = f"{path_key}[{idx}]"
        if not _expect_type(item, dict, item_path, errors, "dict"):
            continue

        template_key = item.get("__template_key") or item.get("template")
        if not template_key:
            errors.append(f"缺少模板选择 {item_path}: 需要 __template_key")
            continue

        template_meta = templates.get(template_key)
        if not template_meta:
            errors.append(f"未知模板 {item_path}: {template_key}")
            continue

        validate_fn(
            item,
            template_meta.get("items", {}),
            path=f"{item_path}.",
        )


def validate_config(data, schema: dict, is_core: bool) -> tuple[list[str], dict]:
    errors = []

    def validate(data: dict, metadata: dict = schema, path=""):
        for key, value in data.items():
            if key not in metadata:
                continue
            meta = metadata[key]
            if "type" not in meta:
                logger.debug(f"配置项 {path}{key} 没有类型定义, 跳过校验")
                continue
            # null 转换
            if value is None:
                data[key] = DEFAULT_VALUE_MAP[meta["type"]]
                continue

            if meta["type"] == "template_list":
                _validate_template_list(value, meta, f"{path}{key}", errors, validate)
                continue

            if meta["type"] == "list" and not isinstance(value, list):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}",
                )
            elif (
                meta["type"] == "list"
                and isinstance(value, list)
                and value
                and "items" in meta
                and isinstance(value[0], dict)
            ):
                # 当前仅针对 list[dict] 的情况进行类型校验，以适配 AstrBot 中 platform、provider 的配置
                for item in value:
                    validate(item, meta["items"], path=f"{path}{key}.")
            elif meta["type"] == "object" and isinstance(value, dict):
                validate(value, meta["items"], path=f"{path}{key}.")

            if meta["type"] == "int" and not isinstance(value, int):
                casted = try_cast(value, "int")
                if casted is None:
                    errors.append(
                        f"错误的类型 {path}{key}: 期望是 int, 得到了 {type(value).__name__}",
                    )
                data[key] = casted
            elif meta["type"] == "float" and not isinstance(value, float):
                casted = try_cast(value, "float")
                if casted is None:
                    errors.append(
                        f"错误的类型 {path}{key}: 期望是 float, 得到了 {type(value).__name__}",
                    )
                data[key] = casted
            elif meta["type"] == "bool" and not isinstance(value, bool):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 bool, 得到了 {type(value).__name__}",
                )
            elif meta["type"] in ["string", "text"] and not isinstance(value, str):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 string, 得到了 {type(value).__name__}",
                )
            elif meta["type"] == "list" and not isinstance(value, list):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}",
                )
            elif meta["type"] == "object" and not isinstance(value, dict):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 dict, 得到了 {type(value).__name__}",
                )

    if is_core:
        meta_all = {
            **schema["platform_group"]["metadata"],
            **schema["provider_group"]["metadata"],
            **schema["misc_config_group"]["metadata"],
        }
        validate(data, meta_all)
    else:
        validate(data, schema)

    return errors, data


def save_config(post_config: dict, config: AstrBotConfig, is_core: bool = False):
    """验证并保存配置"""
    errors = None
    logger.info(f"Saving config, is_core={is_core}")
    try:
        if is_core:
            errors, post_config = validate_config(
                post_config,
                CONFIG_METADATA_2,
                is_core,
            )
        else:
            errors, post_config = validate_config(
                post_config, getattr(config, "schema", {}), is_core
            )
    except BaseException as e:
        logger.error(traceback.format_exc())
        logger.warning(f"验证配置时出现异常: {e}")
        raise ValueError(f"验证配置时出现异常: {e}")
    if errors:
        raise ValueError(f"格式校验未通过: {errors}")

    config.save_config(post_config)


class ConfigRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.config: AstrBotConfig = core_lifecycle.astrbot_config
        self._logo_token_cache = {}  # 缓存logo token，避免重复注册
        self.acm = core_lifecycle.astrbot_config_mgr
        self.ucr = core_lifecycle.umop_config_router
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
            "/config/platform/new": ("POST", self.post_new_platform),
            "/config/platform/update": ("POST", self.post_update_platform),
            "/config/platform/delete": ("POST", self.post_delete_platform),
            "/config/platform/list": ("GET", self.get_platform_list),
            "/config/provider/new": ("POST", self.post_new_provider),
            "/config/provider/update": ("POST", self.post_update_provider),
            "/config/provider/delete": ("POST", self.post_delete_provider),
            "/config/provider/template": ("GET", self.get_provider_template),
            "/config/provider/check_one": ("GET", self.check_one_provider_status),
            "/config/provider/list": ("GET", self.get_provider_config_list),
            "/config/provider/model_list": ("GET", self.get_provider_model_list),
            "/config/provider/get_embedding_dim": ("POST", self.get_embedding_dim),
            "/config/provider_sources/models": (
                "GET",
                self.get_provider_source_models,
            ),
            "/config/provider_sources/update": (
                "POST",
                self.update_provider_source,
            ),
            "/config/provider_sources/delete": (
                "POST",
                self.delete_provider_source,
            ),
        }
        self.register_routes()

    async def delete_provider_source(self):
        """删除 provider_source，并更新关联的 providers"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").__dict__

        provider_source_id = post_data.get("id")
        if not provider_source_id:
            return Response().error("缺少 provider_source_id").__dict__

        provider_sources = self.config.get("provider_sources", [])
        target_idx = next(
            (
                i
                for i, ps in enumerate(provider_sources)
                if ps.get("id") == provider_source_id
            ),
            -1,
        )

        if target_idx == -1:
            return Response().error("未找到对应的 provider source").__dict__

        # 删除 provider_source
        del provider_sources[target_idx]

        # 写回配置
        self.config["provider_sources"] = provider_sources

        # 删除引用了该 provider_source 的 providers
        await self.core_lifecycle.provider_manager.delete_provider(
            provider_source_id=provider_source_id
        )

        try:
            save_config(self.config, self.config, is_core=True)
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

        return Response().ok(message="删除 provider source 成功").__dict__

    async def update_provider_source(self):
        """更新或新增 provider_source，并重载关联的 providers"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").__dict__

        new_source_config = post_data.get("config") or post_data
        original_id = post_data.get("original_id")
        if not original_id:
            return Response().error("缺少 original_id").__dict__

        if not isinstance(new_source_config, dict):
            return Response().error("缺少或错误的配置数据").__dict__

        # 确保配置中有 id 字段
        if not new_source_config.get("id"):
            new_source_config["id"] = original_id

        provider_sources = self.config.get("provider_sources", [])

        for ps in provider_sources:
            if ps.get("id") == new_source_config["id"] and ps.get("id") != original_id:
                return (
                    Response()
                    .error(
                        f"Provider source ID '{new_source_config['id']}' exists already, please try another ID.",
                    )
                    .__dict__
                )

        # 查找旧的 provider_source，若不存在则追加为新配置
        target_idx = next(
            (i for i, ps in enumerate(provider_sources) if ps.get("id") == original_id),
            -1,
        )

        old_id = original_id
        if target_idx == -1:
            provider_sources.append(new_source_config)
        else:
            old_id = provider_sources[target_idx].get("id")
            provider_sources[target_idx] = new_source_config

        # 更新引用了该 provider_source 的 providers
        affected_providers = []
        for provider in self.config.get("provider", []):
            if provider.get("provider_source_id") == old_id:
                provider["provider_source_id"] = new_source_config["id"]
                affected_providers.append(provider)

        # 写回配置
        self.config["provider_sources"] = provider_sources

        try:
            save_config(self.config, self.config, is_core=True)
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

        # 重载受影响的 providers，使新的 source 配置生效
        reload_errors = []
        prov_mgr = self.core_lifecycle.provider_manager
        for provider in affected_providers:
            try:
                await prov_mgr.reload(provider)
            except Exception as e:
                logger.error(traceback.format_exc())
                reload_errors.append(f"{provider.get('id')}: {e}")

        if reload_errors:
            return (
                Response()
                .error("更新成功，但部分提供商重载失败: " + ", ".join(reload_errors))
                .__dict__
            )

        return Response().ok(message="更新 provider source 成功").__dict__

    async def get_provider_template(self):
        config_schema = {
            "provider": CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]
        }
        data = {
            "config_schema": config_schema,
            "providers": astrbot_config["provider"],
            "provider_sources": astrbot_config["provider_sources"],
        }
        return Response().ok(data=data).__dict__

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

    async def _test_single_provider(self, provider):
        """辅助函数：测试单个 provider 的可用性"""
        meta = provider.meta()
        provider_name = provider.provider_config.get("id", "Unknown Provider")
        provider_capability_type = meta.provider_type

        status_info = {
            "id": getattr(meta, "id", "Unknown ID"),
            "model": getattr(meta, "model", "Unknown Model"),
            "type": provider_capability_type.value,
            "name": provider_name,
            "status": "unavailable",  # 默认为不可用
            "error": None,
        }
        logger.debug(
            f"Attempting to check provider: {status_info['name']} (ID: {status_info['id']}, Type: {status_info['type']}, Model: {status_info['model']})",
        )

        try:
            await provider.test()
            status_info["status"] = "available"
            logger.info(
                f"Provider {status_info['name']} (ID: {status_info['id']}) is available.",
            )
        except Exception as e:
            error_message = str(e)
            status_info["error"] = error_message
            logger.warning(
                f"Provider {status_info['name']} (ID: {status_info['id']}) is unavailable. Error: {error_message}",
            )
            logger.debug(
                f"Traceback for {status_info['name']}:\n{traceback.format_exc()}",
            )

        return status_info

    def _error_response(
        self,
        message: str,
        status_code: int = 500,
        log_fn=logger.error,
    ):
        log_fn(message)
        # 记录更详细的traceback信息，但只在是严重错误时
        if status_code == 500:
            log_fn(traceback.format_exc())
        return Response().error(message).__dict__

    async def check_one_provider_status(self):
        """API: check a single LLM Provider's status by id"""
        provider_id = request.args.get("id")
        if not provider_id:
            return self._error_response(
                "Missing provider_id parameter",
                400,
                logger.warning,
            )

        logger.info(f"API call: /config/provider/check_one id={provider_id}")
        try:
            prov_mgr = self.core_lifecycle.provider_manager
            target = prov_mgr.inst_map.get(provider_id)

            if not target:
                logger.warning(
                    f"Provider with id '{provider_id}' not found in provider_manager.",
                )
                return (
                    Response()
                    .error(f"Provider with id '{provider_id}' not found")
                    .__dict__
                )

            result = await self._test_single_provider(target)
            return Response().ok(result).__dict__

        except Exception as e:
            return self._error_response(
                f"Critical error checking provider {provider_id}: {e}",
                500,
            )

    async def get_configs(self):
        # plugin_name 为空时返回 AstrBot 配置
        # 否则返回指定 plugin_name 的插件配置
        plugin_name = request.args.get("plugin_name", None)
        if not plugin_name:
            return Response().ok(await self._get_astrbot_config()).__dict__
        return Response().ok(await self._get_plugin_config(plugin_name)).__dict__

    async def get_provider_config_list(self):
        provider_type = request.args.get("provider_type", None)
        if not provider_type:
            return Response().error("缺少参数 provider_type").__dict__
        provider_type_ls = provider_type.split(",")
        provider_list = []
        ps = self.core_lifecycle.provider_manager.providers_config
        p_source_pt = {
            psrc["id"]: psrc.get("provider_type", "chat_completion")
            for psrc in self.core_lifecycle.provider_manager.provider_sources_config
        }
        for provider in ps:
            ps_id = provider.get("provider_source_id", None)
            if (
                ps_id
                and ps_id in p_source_pt
                and p_source_pt[ps_id] in provider_type_ls
            ):
                # chat
                prov = self.core_lifecycle.provider_manager.get_merged_provider_config(
                    provider
                )
                provider_list.append(prov)
            elif not ps_id and provider.get("provider_type", "") in provider_type_ls:
                # agent runner, embedding, etc
                provider_list.append(provider)
        return Response().ok(provider_list).__dict__

    async def get_provider_model_list(self):
        """获取指定提供商的模型列表"""
        provider_id = request.args.get("provider_id", None)
        if not provider_id:
            return Response().error("缺少参数 provider_id").__dict__

        prov_mgr = self.core_lifecycle.provider_manager
        provider = prov_mgr.inst_map.get(provider_id, None)
        if not provider:
            return Response().error(f"未找到 ID 为 {provider_id} 的提供商").__dict__
        if not isinstance(provider, Provider):
            return (
                Response()
                .error(f"提供商 {provider_id} 类型不支持获取模型列表")
                .__dict__
            )

        try:
            models = await provider.get_models()
            models = models or []

            metadata_map = {}
            for model_id in models:
                meta = LLM_METADATAS.get(model_id)
                if meta:
                    metadata_map[model_id] = meta

            ret = {
                "models": models,
                "provider_id": provider_id,
                "model_metadata": metadata_map,
            }
            return Response().ok(ret).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def get_embedding_dim(self):
        """获取嵌入模型的维度"""
        post_data = await request.json
        provider_config = post_data.get("provider_config", None)
        if not provider_config:
            return Response().error("缺少参数 provider_config").__dict__

        try:
            # 动态导入 EmbeddingProvider
            from astrbot.core.provider.provider import EmbeddingProvider
            from astrbot.core.provider.register import provider_cls_map

            # 获取 provider 类型
            provider_type = provider_config.get("type", None)
            if not provider_type:
                return Response().error("provider_config 缺少 type 字段").__dict__

            # 获取对应的 provider 类
            if provider_type not in provider_cls_map:
                return (
                    Response()
                    .error(f"未找到适用于 {provider_type} 的提供商适配器")
                    .__dict__
                )

            provider_metadata = provider_cls_map[provider_type]
            cls_type = provider_metadata.cls_type

            if not cls_type:
                return Response().error(f"无法找到 {provider_type} 的类").__dict__

            # 实例化 provider
            inst = cls_type(provider_config, {})

            # 检查是否是 EmbeddingProvider
            if not isinstance(inst, EmbeddingProvider):
                return Response().error("提供商不是 EmbeddingProvider 类型").__dict__

            init_fn = getattr(inst, "initialize", None)
            if inspect.iscoroutinefunction(init_fn):
                await init_fn()

            # 获取嵌入向量维度
            vec = await inst.get_embedding("echo")
            dim = len(vec)

            logger.info(
                f"检测到 {provider_config.get('id', 'unknown')} 的嵌入向量维度为 {dim}",
            )

            return Response().ok({"embedding_dimensions": dim}).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"获取嵌入维度失败: {e!s}").__dict__

    async def get_provider_source_models(self):
        """获取指定 provider_source 支持的模型列表

        本质上会临时初始化一个 Provider 实例，调用 get_models() 获取模型列表，然后销毁实例
        """
        provider_source_id = request.args.get("source_id")
        if not provider_source_id:
            return Response().error("缺少参数 source_id").__dict__

        try:
            from astrbot.core.provider.register import provider_cls_map

            # 从配置中查找对应的 provider_source
            provider_sources = self.config.get("provider_sources", [])
            provider_source = None
            for ps in provider_sources:
                if ps.get("id") == provider_source_id:
                    provider_source = ps
                    break

            if not provider_source:
                return (
                    Response()
                    .error(f"未找到 ID 为 {provider_source_id} 的 provider_source")
                    .__dict__
                )

            # 获取 provider 类型
            provider_type = provider_source.get("type", None)
            if not provider_type:
                return Response().error("provider_source 缺少 type 字段").__dict__

            try:
                self.core_lifecycle.provider_manager.dynamic_import_provider(
                    provider_type
                )
            except ImportError as e:
                logger.error(traceback.format_exc())
                return Response().error(f"动态导入提供商适配器失败: {e!s}").__dict__

            # 获取对应的 provider 类
            if provider_type not in provider_cls_map:
                return (
                    Response()
                    .error(f"未找到适用于 {provider_type} 的提供商适配器")
                    .__dict__
                )

            provider_metadata = provider_cls_map[provider_type]
            cls_type = provider_metadata.cls_type

            if not cls_type:
                return Response().error(f"无法找到 {provider_type} 的类").__dict__

            # 检查是否是 Provider 类型
            if not issubclass(cls_type, Provider):
                return (
                    Response()
                    .error(f"提供商 {provider_type} 不支持获取模型列表")
                    .__dict__
                )

            # 临时实例化 provider
            inst = cls_type(provider_source, {})

            # 如果有 initialize 方法，调用它
            init_fn = getattr(inst, "initialize", None)
            if inspect.iscoroutinefunction(init_fn):
                await init_fn()

            # 获取模型列表
            models = await inst.get_models()
            models = models or []

            metadata_map = {}
            for model_id in models:
                meta = LLM_METADATAS.get(model_id)
                if meta:
                    metadata_map[model_id] = meta

            # 销毁实例（如果有 terminate 方法）
            terminate_fn = getattr(inst, "terminate", None)
            if inspect.iscoroutinefunction(terminate_fn):
                await terminate_fn()

            logger.info(
                f"获取到 provider_source {provider_source_id} 的模型列表: {models}",
            )

            return (
                Response()
                .ok({"models": models, "model_metadata": metadata_map})
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"获取模型列表失败: {e!s}").__dict__

    async def get_platform_list(self):
        """获取所有平台的列表"""
        platform_list = []
        for platform in self.config["platform"]:
            platform_list.append(platform)
        return Response().ok({"platforms": platform_list}).__dict__

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

    async def post_new_platform(self):
        new_platform_config = await request.json

        # 如果是支持统一 webhook 模式的平台，生成 webhook_uuid
        ensure_platform_webhook_config(new_platform_config)

        self.config["platform"].append(new_platform_config)
        try:
            save_config(self.config, self.config, is_core=True)
            await self.core_lifecycle.platform_manager.load_platform(
                new_platform_config,
            )
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "新增平台配置成功~").__dict__

    async def post_new_provider(self):
        new_provider_config = await request.json

        try:
            await self.core_lifecycle.provider_manager.create_provider(
                new_provider_config
            )
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "新增服务提供商配置成功").__dict__

    async def post_update_platform(self):
        update_platform_config = await request.json
        origin_platform_id = update_platform_config.get("id", None)
        new_config = update_platform_config.get("config", None)
        if not origin_platform_id or not new_config:
            return Response().error("参数错误").__dict__

        if origin_platform_id != new_config.get("id", None):
            return Response().error("机器人名称不允许修改").__dict__

        # 如果是支持统一 webhook 模式的平台，且启用了统一 webhook 模式，确保有 webhook_uuid
        ensure_platform_webhook_config(new_config)

        for i, platform in enumerate(self.config["platform"]):
            if platform["id"] == origin_platform_id:
                self.config["platform"][i] = new_config
                break
        else:
            return Response().error("未找到对应平台").__dict__

        try:
            save_config(self.config, self.config, is_core=True)
            await self.core_lifecycle.platform_manager.reload(new_config)
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "更新平台配置成功~").__dict__

    async def post_update_provider(self):
        update_provider_config = await request.json
        origin_provider_id = update_provider_config.get("id", None)
        new_config = update_provider_config.get("config", None)
        if not origin_provider_id or not new_config:
            return Response().error("参数错误").__dict__

        try:
            await self.core_lifecycle.provider_manager.update_provider(
                origin_provider_id, new_config
            )
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "更新成功，已经实时生效~").__dict__

    async def post_delete_platform(self):
        platform_id = await request.json
        platform_id = platform_id.get("id")
        for i, platform in enumerate(self.config["platform"]):
            if platform["id"] == platform_id:
                del self.config["platform"][i]
                break
        else:
            return Response().error("未找到对应平台").__dict__
        try:
            save_config(self.config, self.config, is_core=True)
            await self.core_lifecycle.platform_manager.terminate_platform(platform_id)
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "删除平台配置成功~").__dict__

    async def post_delete_provider(self):
        provider_id = await request.json
        provider_id = provider_id.get("id", "")
        if not provider_id:
            return Response().error("缺少参数 id").__dict__

        try:
            await self.core_lifecycle.provider_manager.delete_provider(
                provider_id=provider_id
            )
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "删除成功，已经实时生效。").__dict__

    async def get_llm_tools(self):
        """获取函数调用工具。包含了本地加载的以及 MCP 服务的工具"""
        tool_mgr = self.core_lifecycle.provider_manager.llm_tools
        tools = tool_mgr.get_func_desc_openai_style()
        return Response().ok(tools).__dict__

    async def _register_platform_logo(self, platform, platform_default_tmpl):
        """注册平台logo文件并生成访问令牌"""
        if not platform.logo_path:
            return

        try:
            # 检查缓存
            cache_key = f"{platform.name}:{platform.logo_path}"
            if cache_key in self._logo_token_cache:
                cached_token = self._logo_token_cache[cache_key]
                # 确保platform_default_tmpl[platform.name]存在且为字典
                if platform.name not in platform_default_tmpl or not isinstance(
                    platform_default_tmpl[platform.name], dict
                ):
                    platform_default_tmpl[platform.name] = {}
                platform_default_tmpl[platform.name]["logo_token"] = cached_token
                logger.debug(f"Using cached logo token for platform {platform.name}")
                return

            # 获取平台适配器类
            platform_cls = platform_cls_map.get(platform.name)
            if not platform_cls:
                logger.warning(f"Platform class not found for {platform.name}")
                return

            # 获取插件目录路径
            module_file = inspect.getfile(platform_cls)
            plugin_dir = os.path.dirname(module_file)

            # 解析logo文件路径
            logo_file_path = os.path.join(plugin_dir, platform.logo_path)

            # 检查文件是否存在并注册令牌
            if os.path.exists(logo_file_path):
                logo_token = await file_token_service.register_file(
                    logo_file_path,
                    timeout=3600,
                )

                # 确保platform_default_tmpl[platform.name]存在且为字典
                if platform.name not in platform_default_tmpl or not isinstance(
                    platform_default_tmpl[platform.name], dict
                ):
                    platform_default_tmpl[platform.name] = {}

                platform_default_tmpl[platform.name]["logo_token"] = logo_token

                # 缓存token
                self._logo_token_cache[cache_key] = logo_token

                logger.debug(f"Logo token registered for platform {platform.name}")
            else:
                logger.warning(
                    f"Platform {platform.name} logo file not found: {logo_file_path}",
                )

        except (ImportError, AttributeError) as e:
            logger.warning(
                f"Failed to import required modules for platform {platform.name}: {e}",
            )
        except OSError as e:
            logger.warning(f"File system error for platform {platform.name} logo: {e}")
        except Exception as e:
            logger.warning(
                f"Unexpected error registering logo for platform {platform.name}: {e}",
            )

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
                        self._register_platform_logo(platform, platform_default_tmpl),
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
