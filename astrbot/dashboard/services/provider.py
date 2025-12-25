import inspect
import traceback

from quart import request

from astrbot.core import astrbot_config, logger
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.provider import EmbeddingProvider, Provider
from astrbot.core.utils.llm_metadata import LLM_METADATAS

from ..entities import Response
from . import BaseService
from .utils import save_config


class ProviderService(BaseService):
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

        provider_sources = astrbot_config.get("provider_sources", [])

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
        for provider in astrbot_config.get("provider", []):
            if provider.get("provider_source_id") == old_id:
                provider["provider_source_id"] = new_source_config["id"]
                affected_providers.append(provider)

        # 写回配置
        astrbot_config["provider_sources"] = provider_sources

        try:
            save_config(astrbot_config, astrbot_config, is_core=True)
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

        # 重载受影响的 providers，使新的 source 配置生效
        reload_errors = []
        for provider in affected_providers:
            try:
                await self.clpm.reload(provider)
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

    async def delete_provider_source(self):
        """删除 provider_source，并更新关联的 providers"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").__dict__

        provider_source_id = post_data.get("id")
        if not provider_source_id:
            return Response().error("缺少 provider_source_id").__dict__

        provider_sources = astrbot_config.get("provider_sources", [])
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
        astrbot_config["provider_sources"] = provider_sources

        # 删除引用了该 provider_source 的 providers
        await self.clpm.delete_provider(provider_source_id=provider_source_id)

        try:
            save_config(astrbot_config, astrbot_config, is_core=True)
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

        return Response().ok(message="删除 provider source 成功").__dict__

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
            provider_sources = astrbot_config.get("provider_sources", [])
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
                self.clpm.dynamic_import_provider(provider_type)
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

    async def get_provider_template(self):
        """获取 provider 配置模板"""
        config_schema = {
            "provider": CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]
        }
        data = {
            "config_schema": config_schema,
            "providers": astrbot_config["provider"],
            "provider_sources": astrbot_config["provider_sources"],
        }
        return Response().ok(data=data).__dict__

    async def list_provider_sources(self):
        """获取 provider source 列表"""
        return Response().ok(data=astrbot_config["provider_sources"]).__dict__

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
            prov_mgr = self.clpm
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

    async def get_provider_config_list(self):
        """获取指定类型的 provider 配置列表"""
        provider_type = request.args.get("provider_type", None)
        if not provider_type:
            return Response().error("缺少参数 provider_type").__dict__
        provider_type_ls = provider_type.split(",")
        provider_list = []
        ps = self.clpm.providers_config
        p_source_pt = {
            psrc["id"]: psrc["provider_type"]
            for psrc in self.clpm.provider_sources_config
        }
        for provider in ps:
            ps_id = provider.get("provider_source_id", None)
            if (
                ps_id
                and ps_id in p_source_pt
                and p_source_pt[ps_id] in provider_type_ls
            ):
                # chat
                prov = self.clpm.get_merged_provider_config(provider)
                provider_list.append(prov)
            elif not ps_id and provider.get("provider_type", None) in provider_type_ls:
                # agent runner, embedding, etc
                provider_list.append(provider)
        return Response().ok(provider_list).__dict__

    async def get_embedding_dim(self):
        """获取嵌入模型的维度"""
        post_data = await request.json
        provider_config = post_data.get("provider_config", None)
        if not provider_config:
            return Response().error("缺少参数 provider_config").__dict__

        try:
            # 动态导入 EmbeddingProvider
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

    async def post_new_provider(self):
        """创建新的 provider"""
        new_provider_config = await request.json

        try:
            await self.clpm.create_provider(new_provider_config)
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "新增服务提供商配置成功").__dict__

    async def post_update_provider(self):
        """更新 provider 配置"""
        update_provider_config = await request.json
        origin_provider_id = update_provider_config.get("id", None)
        new_config = update_provider_config.get("config", None)
        if not origin_provider_id or not new_config:
            return Response().error("参数错误").__dict__

        try:
            await self.clpm.update_provider(origin_provider_id, new_config)
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "更新成功，已经实时生效~").__dict__

    async def post_delete_provider(self):
        """删除 provider"""
        provider_id = await request.json
        provider_id = provider_id.get("id", "")
        if not provider_id:
            return Response().error("缺少参数 id").__dict__

        try:
            await self.clpm.delete_provider(provider_id=provider_id)
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "删除成功，已经实时生效。").__dict__
