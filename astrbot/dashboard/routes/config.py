import typing
import traceback
import os
from .route import Route, Response, RouteContext
from astrbot.core.provider.entities import ProviderType
from quart import request
from astrbot.core.config.default import CONFIG_METADATA_2, DEFAULT_VALUE_MAP
from astrbot.core.utils.astrbot_path import get_astrbot_path
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.platform.register import platform_registry
from astrbot.core.provider.register import provider_registry
from astrbot.core.star.star import star_registry
from astrbot.core import logger
from astrbot.core.provider import Provider
import asyncio


def try_cast(value: str, type_: str):
    if type_ == "int":
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    elif (
        type_ == "float"
        and isinstance(value, str)
        and value.replace(".", "", 1).isdigit()
    ):
        return float(value)
    elif type_ == "float" and isinstance(value, int):
        return float(value)
    elif type_ == "float":
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


def validate_config(
    data, schema: dict, is_core: bool
) -> typing.Tuple[typing.List[str], typing.Dict]:
    errors = []

    def validate(data: dict, metadata: dict = schema, path=""):
        for key, value in data.items():
            if key not in metadata:
                # 无 schema 的配置项，执行类型猜测
                if isinstance(value, str):
                    try:
                        data[key] = int(value)
                        continue
                    except ValueError:
                        pass

                    try:
                        data[key] = float(value)
                        continue
                    except ValueError:
                        pass

                    if value.lower() == "true":
                        data[key] = True
                    elif value.lower() == "false":
                        data[key] = False
                continue
            meta = metadata[key]
            if "type" not in meta:
                logger.debug(f"配置项 {path}{key} 没有类型定义, 跳过校验")
                continue
            # null 转换
            if value is None:
                data[key] = DEFAULT_VALUE_MAP[meta["type"]]
                continue
            if meta["type"] == "list" and not isinstance(value, list):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}"
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
                        f"错误的类型 {path}{key}: 期望是 int, 得到了 {type(value).__name__}"
                    )
                data[key] = casted
            elif meta["type"] == "float" and not isinstance(value, float):
                casted = try_cast(value, "float")
                if casted is None:
                    errors.append(
                        f"错误的类型 {path}{key}: 期望是 float, 得到了 {type(value).__name__}"
                    )
                data[key] = casted
            elif meta["type"] == "bool" and not isinstance(value, bool):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 bool, 得到了 {type(value).__name__}"
                )
            elif meta["type"] in ["string", "text"] and not isinstance(value, str):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 string, 得到了 {type(value).__name__}"
                )
            elif meta["type"] == "list" and not isinstance(value, list):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}"
                )
            elif meta["type"] == "object" and not isinstance(value, dict):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 dict, 得到了 {type(value).__name__}"
                )

    if is_core:
        for key, group in schema.items():
            group_meta = group.get("metadata")
            if not group_meta:
                continue
            # logger.info(f"验证配置: 组 {key} ...")
            validate(data, group_meta, path=f"{key}.")
    else:
        validate(data, schema)

    return errors, data


def save_config(post_config: dict, config: AstrBotConfig, is_core: bool = False):
    """验证并保存配置"""
    errors = None
    try:
        if is_core:
            errors, post_config = validate_config(
                post_config, CONFIG_METADATA_2, is_core
            )
        else:
            errors, post_config = validate_config(post_config, config.schema, is_core)
    except BaseException as e:
        logger.error(traceback.format_exc())
        logger.warning(f"验证配置时出现异常: {e}")
        raise ValueError(f"验证配置时出现异常: {e}")
    if errors:
        raise ValueError(f"格式校验未通过: {errors}")
    config.save_config(post_config)


class ConfigRoute(Route):
    def __init__(
        self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.config: AstrBotConfig = core_lifecycle.astrbot_config
        self.routes = {
            "/config/get": ("GET", self.get_configs),
            "/config/astrbot/update": ("POST", self.post_astrbot_configs),
            "/config/plugin/update": ("POST", self.post_plugin_configs),
            "/config/platform/new": ("POST", self.post_new_platform),
            "/config/platform/update": ("POST", self.post_update_platform),
            "/config/platform/delete": ("POST", self.post_delete_platform),
            "/config/provider/new": ("POST", self.post_new_provider),
            "/config/provider/update": ("POST", self.post_update_provider),
            "/config/provider/delete": ("POST", self.post_delete_provider),
            "/config/llmtools": ("GET", self.get_llm_tools),
            "/config/provider/check_one": ("GET", self.check_one_provider_status),
            "/config/provider/list": ("GET", self.get_provider_config_list),
            "/config/provider/model_list": ("GET", self.get_provider_model_list),
            "/config/provider/get_session_seperate": (
                "GET",
                lambda: Response()
                .ok({"enable": self.config["provider_settings"]["separate_provider"]})
                .__dict__,
            ),
            "/config/provider/set_session_seperate": (
                "POST",
                self.post_session_seperate,
            ),
        }
        self.register_routes()

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
            f"Attempting to check provider: {status_info['name']} (ID: {status_info['id']}, Type: {status_info['type']}, Model: {status_info['model']})"
        )

        if provider_capability_type == ProviderType.CHAT_COMPLETION:
            try:
                logger.debug(f"Sending 'Ping' to provider: {status_info['name']}")
                response = await asyncio.wait_for(
                    provider.text_chat(prompt="REPLY `PONG` ONLY"), timeout=45.0
                )
                logger.debug(f"Received response from {status_info['name']}: {response}")
                if response is not None:
                    status_info["status"] = "available"
                    response_text_snippet = ""
                    if hasattr(response, "completion_text") and response.completion_text:
                        response_text_snippet = (
                            response.completion_text[:70] + "..."
                            if len(response.completion_text) > 70
                            else response.completion_text
                        )
                    elif hasattr(response, "result_chain") and response.result_chain:
                        try:
                            response_text_snippet = (
                                response.result_chain.get_plain_text()[:70] + "..."
                                if len(response.result_chain.get_plain_text()) > 70
                                else response.result_chain.get_plain_text()
                            )
                        except Exception as _:
                            pass
                    logger.info(
                        f"Provider {status_info['name']} (ID: {status_info['id']}) is available. Response snippet: '{response_text_snippet}'"
                    )
                else:
                    status_info["error"] = "Test call returned None, but expected an LLMResponse object."
                    logger.warning(f"Provider {status_info['name']} (ID: {status_info['id']}) test call returned None.")

            except asyncio.TimeoutError:
                status_info["error"] = "Connection timed out after 45 seconds during test call."
                logger.warning(f"Provider {status_info['name']} (ID: {status_info['id']}) timed out.")
            except Exception as e:
                error_message = str(e)
                status_info["error"] = error_message
                logger.warning(f"Provider {status_info['name']} (ID: {status_info['id']}) is unavailable. Error: {error_message}")
                logger.debug(f"Traceback for {status_info['name']}:\n{traceback.format_exc()}")

        elif provider_capability_type == ProviderType.EMBEDDING:
            try:
                # For embedding, we can call the get_embedding method with a short prompt.
                embedding_result = await provider.get_embedding("health_check")
                if isinstance(embedding_result, list) and (not embedding_result or isinstance(embedding_result[0], float)):
                    status_info["status"] = "available"
                else:
                    status_info["status"] = "unavailable"
                    status_info["error"] = f"Embedding test failed: unexpected result type {type(embedding_result)}"
            except Exception as e:
                logger.error(f"Error testing embedding provider {provider_name}: {e}", exc_info=True)
                status_info["status"] = "unavailable"
                status_info["error"] = f"Embedding test failed: {str(e)}"

        elif provider_capability_type == ProviderType.TEXT_TO_SPEECH:
            try:
                # For TTS, we can call the get_audio method with a short prompt.
                audio_result = await provider.get_audio("你好")
                if isinstance(audio_result, str) and audio_result:
                    status_info["status"] = "available"
                else:
                    status_info["status"] = "unavailable"
                    status_info["error"] = f"TTS test failed: unexpected result type {type(audio_result)}"
            except Exception as e:
                logger.error(f"Error testing TTS provider {provider_name}: {e}", exc_info=True)
                status_info["status"] = "unavailable"
                status_info["error"] = f"TTS test failed: {str(e)}"
        elif provider_capability_type == ProviderType.SPEECH_TO_TEXT:
            try:
                logger.debug(f"Sending health check audio to provider: {status_info['name']}")
                sample_audio_path = os.path.join(get_astrbot_path(), "samples", "stt_health_check.wav")
                if not os.path.exists(sample_audio_path):
                    status_info["status"] = "unavailable"
                    status_info["error"] = "STT test failed: sample audio file not found."
                    logger.warning(f"STT test for {status_info['name']} failed: sample audio file not found at {sample_audio_path}")
                else:
                    text_result = await provider.get_text(sample_audio_path)
                    if isinstance(text_result, str) and text_result:
                        status_info["status"] = "available"
                        snippet = text_result[:70] + "..." if len(text_result) > 70 else text_result
                        logger.info(f"Provider {status_info['name']} (ID: {status_info['id']}) is available. Response snippet: '{snippet}'")
                    else:
                        status_info["status"] = "unavailable"
                        status_info["error"] = f"STT test failed: unexpected result type {type(text_result)}"
                        logger.warning(f"STT test for {status_info['name']} failed: unexpected result type {type(text_result)}")
            except Exception as e:
                logger.error(f"Error testing STT provider {provider_name}: {e}", exc_info=True)
                status_info["status"] = "unavailable"
                status_info["error"] = f"STT test failed: {str(e)}"
        else:
            logger.debug(f"Provider {provider_name} is not a Chat Completion or Embedding provider. Marking as available without test. Meta: {meta}")
            status_info["status"] = "available"
            status_info["error"] = "This provider type is not tested and is assumed to be available."

        return status_info

    def _error_response(self, message: str, status_code: int = 500, log_fn=logger.error):
        log_fn(message)
        # 记录更详细的traceback信息，但只在是严重错误时
        if status_code == 500:
            log_fn(traceback.format_exc())
        return Response().error(message).__dict__

    async def check_one_provider_status(self):
        """API: check a single LLM Provider's status by id"""
        provider_id = request.args.get("id")
        if not provider_id:
            return self._error_response("Missing provider_id parameter", 400, logger.warning)

        logger.info(f"API call: /config/provider/check_one id={provider_id}")
        try:
            prov_mgr = self.core_lifecycle.provider_manager
            target = prov_mgr.inst_map.get(provider_id)

            if not target:
                logger.warning(f"Provider with id '{provider_id}' not found in provider_manager.")
                return Response().error(f"Provider with id '{provider_id}' not found").__dict__

            result = await self._test_single_provider(target)
            return Response().ok(result).__dict__

        except Exception as e:
            return self._error_response(
                f"Critical error checking provider {provider_id}: {e}",
                500
            )

    async def get_configs(self):
        # plugin_name 为空时返回 AstrBot 配置
        # 否则返回指定 plugin_name 的插件配置
        plugin_name = request.args.get("plugin_name", None)
        if not plugin_name:
            return Response().ok(await self._get_astrbot_config()).__dict__
        return Response().ok(await self._get_plugin_config(plugin_name)).__dict__

    async def post_session_seperate(self):
        """设置提供商会话隔离"""
        post_config = await request.json
        enable = post_config.get("enable", None)
        if enable is None:
            return Response().error("缺少参数 enable").__dict__

        astrbot_config = self.core_lifecycle.astrbot_config
        astrbot_config["provider_settings"]["separate_provider"] = enable
        try:
            astrbot_config.save_config()
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "设置成功~").__dict__

    async def get_provider_config_list(self):
        provider_type = request.args.get("provider_type", None)
        if not provider_type:
            return Response().error("缺少参数 provider_type").__dict__
        provider_list = []
        astrbot_config = self.core_lifecycle.astrbot_config
        for provider in astrbot_config["provider"]:
            if provider.get("provider_type", None) == provider_type:
                provider_list.append(provider)
        return Response().ok(provider_list).__dict__

    async def get_provider_model_list(self):
        """获取指定提供商的模型列表"""
        provider_id = request.args.get("provider_id", None)
        if not provider_id:
            return Response().error("缺少参数 provider_id").__dict__

        prov_mgr = self.core_lifecycle.provider_manager
        provider: Provider | None = prov_mgr.inst_map.get(provider_id, None)
        if not provider:
            return Response().error(f"未找到 ID 为 {provider_id} 的提供商").__dict__

        try:
            models = await provider.get_models()
            ret = {
                "models": models,
                "provider_id": provider_id,
            }
            return Response().ok(ret).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def post_astrbot_configs(self):
        post_configs = await request.json
        try:
            await self._save_astrbot_configs(post_configs)
            return Response().ok(None, "保存成功~ 机器人正在重载配置。").__dict__
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
        self.config["platform"].append(new_platform_config)
        try:
            save_config(self.config, self.config, is_core=True)
            await self.core_lifecycle.platform_manager.load_platform(
                new_platform_config
            )
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "新增平台配置成功~").__dict__

    async def post_new_provider(self):
        new_provider_config = await request.json
        self.config["provider"].append(new_provider_config)
        try:
            save_config(self.config, self.config, is_core=True)
            await self.core_lifecycle.provider_manager.load_provider(
                new_provider_config
            )
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "新增服务提供商配置成功~").__dict__

    async def post_update_platform(self):
        update_platform_config = await request.json
        platform_id = update_platform_config.get("id", None)
        new_config = update_platform_config.get("config", None)
        if not platform_id or not new_config:
            return Response().error("参数错误").__dict__

        for i, platform in enumerate(self.config["platform"]):
            if platform["id"] == platform_id:
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
        provider_id = update_provider_config.get("id", None)
        new_config = update_provider_config.get("config", None)
        if not provider_id or not new_config:
            return Response().error("参数错误").__dict__

        for i, provider in enumerate(self.config["provider"]):
            if provider["id"] == provider_id:
                self.config["provider"][i] = new_config
                break
        else:
            return Response().error("未找到对应服务提供商").__dict__

        try:
            save_config(self.config, self.config, is_core=True)
            await self.core_lifecycle.provider_manager.reload(new_config)
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
        provider_id = provider_id.get("id")
        for i, provider in enumerate(self.config["provider"]):
            if provider["id"] == provider_id:
                del self.config["provider"][i]
                break
        else:
            return Response().error("未找到对应服务提供商").__dict__
        try:
            save_config(self.config, self.config, is_core=True)
            await self.core_lifecycle.provider_manager.terminate_provider(provider_id)
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "删除成功，已经实时生效~").__dict__

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
        for platform in platform_registry:
            if platform.default_config_tmpl:
                platform_default_tmpl[platform.name] = platform.default_config_tmpl

        # 服务提供商的默认配置模板注入
        provider_default_tmpl = CONFIG_METADATA_2["provider_group"]["metadata"][
            "provider"
        ]["config_template"]
        for provider in provider_registry:
            if provider.default_config_tmpl:
                provider_default_tmpl[provider.type] = provider.default_config_tmpl

        return {"metadata": CONFIG_METADATA_2, "config": config}

    async def _get_plugin_config(self, plugin_name: str):
        ret = {"metadata": None, "config": None}

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
                    }
                }
                break

        return ret

    async def _save_astrbot_configs(self, post_configs: dict):
        try:
            save_config(post_configs, self.config, is_core=True)
            await self.core_lifecycle.restart()
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
