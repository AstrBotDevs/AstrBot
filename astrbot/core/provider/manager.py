import asyncio
import copy
import os
import traceback
from typing import Protocol, runtime_checkable

from astrbot.core import astrbot_config, logger, sp
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.db import BaseDatabase

from ..persona_mgr import PersonaManager
from .entities import ProviderType
from .provider import (
    EmbeddingProvider,
    Provider,
    Providers,
    RerankProvider,
    STTProvider,
    TTSProvider,
)
from .register import llm_tools, provider_cls_map


@runtime_checkable
class HasInitialize(Protocol):
    async def initialize(self) -> None: ...


class ProviderManager:
    def __init__(
        self,
        acm: AstrBotConfigManager,
        db_helper: BaseDatabase,
        persona_mgr: PersonaManager,
    ):
        self.reload_lock = asyncio.Lock()
        self.resource_lock = asyncio.Lock()
        self.persona_mgr = persona_mgr
        self.acm = acm
        config = acm.confs["default"]
        self.providers_config: list = config["provider"]
        self.provider_sources_config: list = config.get("provider_sources", [])
        self.provider_settings: dict = config["provider_settings"]
        self.provider_stt_settings: dict = config.get("provider_stt_settings", {})
        self.provider_tts_settings: dict = config.get("provider_tts_settings", {})

        # 人格相关属性，v4.0.0 版本后被废弃，推荐使用 PersonaManager
        self.default_persona_name = persona_mgr.default_persona

        self.provider_insts: list[Provider] = []
        """加载的 Provider 的实例"""
        self.stt_provider_insts: list[STTProvider] = []
        """加载的 Speech To Text Provider 的实例"""
        self.tts_provider_insts: list[TTSProvider] = []
        """加载的 Text To Speech Provider 的实例"""
        self.embedding_provider_insts: list[EmbeddingProvider] = []
        """加载的 Embedding Provider 的实例"""
        self.rerank_provider_insts: list[RerankProvider] = []
        """加载的 Rerank Provider 的实例"""
        self.inst_map: dict[
            str,
            Providers,
        ] = {}
        """Provider 实例映射. key: provider_id, value: Provider 实例"""
        self.llm_tools = llm_tools

        self.curr_provider_inst: Provider | None = None
        """默认的 Provider 实例。已弃用，请使用 get_using_provider() 方法获取当前使用的 Provider 实例。"""
        self.curr_stt_provider_inst: STTProvider | None = None
        """默认的 Speech To Text Provider 实例。已弃用，请使用 get_using_provider() 方法获取当前使用的 Provider 实例。"""
        self.curr_tts_provider_inst: TTSProvider | None = None
        """默认的 Text To Speech Provider 实例。已弃用，请使用 get_using_provider() 方法获取当前使用的 Provider 实例。"""
        self.db_helper = db_helper

    @property
    def persona_configs(self) -> list:
        """动态获取最新的 persona 配置"""
        return self.persona_mgr.persona_v3_config

    @property
    def personas(self) -> list:
        """动态获取最新的 personas 列表"""
        return self.persona_mgr.personas_v3

    @property
    def selected_default_persona(self):
        """动态获取最新的默认选中 persona。已弃用，请使用 context.persona_mgr.get_default_persona_v3()"""
        return self.persona_mgr.selected_default_persona_v3

    async def set_provider(
        self,
        provider_id: str,
        provider_type: ProviderType,
        umo: str | None = None,
    ):
        """设置提供商。

        Args:
            provider_id (str): 提供商 ID。
            provider_type (ProviderType): 提供商类型。
            umo (str, optional): 用户会话 ID，用于提供商会话隔离。

        Version 4.0.0: 这个版本下已经默认隔离提供商

        """
        if provider_id not in self.inst_map:
            raise ValueError(f"提供商 {provider_id} 不存在，无法设置。")
        if umo:
            await sp.session_put(
                umo,
                f"provider_perf_{provider_type.value}",
                provider_id,
            )
            return
        # 不启用提供商会话隔离模式的情况

        prov = self.inst_map[provider_id]
        if provider_type == ProviderType.TEXT_TO_SPEECH and isinstance(
            prov,
            TTSProvider,
        ):
            self.curr_tts_provider_inst = prov
            await sp.put_async(
                key="curr_provider_tts",
                value=provider_id,
                scope="global",
                scope_id="global",
            )
        elif provider_type == ProviderType.SPEECH_TO_TEXT and isinstance(
            prov,
            STTProvider,
        ):
            self.curr_stt_provider_inst = prov
            await sp.put_async(
                key="curr_provider_stt",
                value=provider_id,
                scope="global",
                scope_id="global",
            )
        elif provider_type == ProviderType.CHAT_COMPLETION and isinstance(
            prov,
            Provider,
        ):
            self.curr_provider_inst = prov
            await sp.put_async(
                key="curr_provider",
                value=provider_id,
                scope="global",
                scope_id="global",
            )

    async def get_provider_by_id(self, provider_id: str) -> Providers | None:
        """根据提供商 ID 获取提供商实例"""
        return self.inst_map.get(provider_id)

    def get_using_provider(
        self, provider_type: ProviderType, umo=None
    ) -> Providers | None:
        """获取正在使用的提供商实例。

        Args:
            provider_type (ProviderType): 提供商类型。
            umo (str, optional): 用户会话 ID，用于提供商会话隔离。

        Returns:
            Provider: 正在使用的提供商实例。

        """
        provider = None
        provider_id = None
        if umo:
            provider_id = sp.get(
                f"provider_perf_{provider_type.value}",
                None,
                scope="umo",
                scope_id=umo,
            )
            if provider_id:
                provider = self.inst_map.get(provider_id)
        if not provider:
            # default setting
            config = self.acm.get_conf(umo)
            if provider_type == ProviderType.CHAT_COMPLETION:
                provider_id = config["provider_settings"].get("default_provider_id")
                provider = self.inst_map.get(provider_id)
                if not provider:
                    provider = self.provider_insts[0] if self.provider_insts else None
            elif provider_type == ProviderType.SPEECH_TO_TEXT:
                provider_id = config["provider_stt_settings"].get("provider_id")
                if not provider_id:
                    return None
                provider = self.inst_map.get(provider_id)
                if not provider:
                    provider = (
                        self.stt_provider_insts[0] if self.stt_provider_insts else None
                    )
            elif provider_type == ProviderType.TEXT_TO_SPEECH:
                provider_id = config["provider_tts_settings"].get("provider_id")
                if not provider_id:
                    return None
                provider = self.inst_map.get(provider_id)
                if not provider:
                    provider = (
                        self.tts_provider_insts[0] if self.tts_provider_insts else None
                    )
            else:
                raise ValueError(f"Unknown provider type: {provider_type}")

        if not provider and provider_id:
            logger.warning(
                f"没有找到 ID 为 {provider_id} 的提供商，这可能是由于您修改了提供商（模型）ID 导致的。"
            )

        return provider

    async def initialize(self):
        # 逐个初始化提供商
        for provider_config in self.providers_config:
            try:
                await self.load_provider(provider_config)
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(e)

        selected_provider_id = await sp.get_async(
            key="curr_provider",
            default=self.provider_settings.get("default_provider_id"),
            scope="global",
            scope_id="global",
        )
        selected_stt_provider_id = await sp.get_async(
            key="curr_provider_stt",
            default=self.provider_stt_settings.get("provider_id"),
            scope="global",
            scope_id="global",
        )
        selected_tts_provider_id = await sp.get_async(
            key="curr_provider_tts",
            default=self.provider_tts_settings.get("provider_id"),
            scope="global",
            scope_id="global",
        )

        temp_provider = (
            self.inst_map.get(selected_provider_id)
            if isinstance(selected_provider_id, str)
            else None
        )
        self.curr_provider_inst = (
            temp_provider if isinstance(temp_provider, Provider) else None
        )
        if not self.curr_provider_inst and self.provider_insts:
            self.curr_provider_inst = self.provider_insts[0]

        temp_stt = (
            self.inst_map.get(selected_stt_provider_id)
            if isinstance(selected_stt_provider_id, str)
            else None
        )
        self.curr_stt_provider_inst = (
            temp_stt if isinstance(temp_stt, STTProvider) else None
        )
        if not self.curr_stt_provider_inst and self.stt_provider_insts:
            self.curr_stt_provider_inst = self.stt_provider_insts[0]

        temp_tts = (
            self.inst_map.get(selected_tts_provider_id)
            if isinstance(selected_tts_provider_id, str)
            else None
        )
        self.curr_tts_provider_inst = (
            temp_tts if isinstance(temp_tts, TTSProvider) else None
        )
        if not self.curr_tts_provider_inst and self.tts_provider_insts:
            self.curr_tts_provider_inst = self.tts_provider_insts[0]

        # 初始化 MCP Client 连接
        asyncio.create_task(self.llm_tools.init_mcp_clients(), name="init_mcp_clients")

    def dynamic_import_provider(self, type: str):
        """动态导入提供商适配器模块

        Args:
            type (str): 提供商请求类型。

        Raises:
            ImportError: 如果提供商类型未知或无法导入对应模块，则抛出异常。
        """
        match type:
            case "openai_chat_completion":
                from .sources.openai_source import (
                    ProviderOpenAIOfficial as ProviderOpenAIOfficial,
                )
            case "zhipu_chat_completion":
                from .sources.zhipu_source import ProviderZhipu as ProviderZhipu
            case "groq_chat_completion":
                from .sources.groq_source import ProviderGroq as ProviderGroq
            case "anthropic_chat_completion":
                from .sources.anthropic_source import (
                    ProviderAnthropic as ProviderAnthropic,
                )
            case "googlegenai_chat_completion":
                from .sources.gemini_source import (
                    ProviderGoogleGenAI as ProviderGoogleGenAI,
                )
            case "sensevoice_stt_selfhost":
                from .sources.sensevoice_selfhosted_source import (
                    ProviderSenseVoiceSTTSelfHost as ProviderSenseVoiceSTTSelfHost,
                )
            case "openai_whisper_api":
                from .sources.whisper_api_source import (
                    ProviderOpenAIWhisperAPI as ProviderOpenAIWhisperAPI,
                )
            case "openai_whisper_selfhost":
                from .sources.whisper_selfhosted_source import (
                    ProviderOpenAIWhisperSelfHost as ProviderOpenAIWhisperSelfHost,
                )
            case "xinference_stt":
                from .sources.xinference_stt_provider import (
                    ProviderXinferenceSTT as ProviderXinferenceSTT,
                )
            case "openai_tts_api":
                from .sources.openai_tts_api_source import (
                    ProviderOpenAITTSAPI as ProviderOpenAITTSAPI,
                )
            case "genie_tts":
                from .sources.genie_tts import (
                    GenieTTSProvider as GenieTTSProvider,
                )
            case "edge_tts":
                from .sources.edge_tts_source import (
                    ProviderEdgeTTS as ProviderEdgeTTS,
                )
            case "gsv_tts_selfhost":
                from .sources.gsv_selfhosted_source import (
                    ProviderGSVTTS as ProviderGSVTTS,
                )
            case "gsvi_tts_api":
                from .sources.gsvi_tts_source import (
                    ProviderGSVITTS as ProviderGSVITTS,
                )
            case "fishaudio_tts_api":
                from .sources.fishaudio_tts_api_source import (
                    ProviderFishAudioTTSAPI as ProviderFishAudioTTSAPI,
                )
            case "dashscope_tts":
                from .sources.dashscope_tts import (
                    ProviderDashscopeTTSAPI as ProviderDashscopeTTSAPI,
                )
            case "azure_tts":
                from .sources.azure_tts_source import (
                    AzureTTSProvider as AzureTTSProvider,
                )
            case "minimax_tts_api":
                from .sources.minimax_tts_api_source import (
                    ProviderMiniMaxTTSAPI as ProviderMiniMaxTTSAPI,
                )
            case "volcengine_tts":
                from .sources.volcengine_tts import (
                    ProviderVolcengineTTS as ProviderVolcengineTTS,
                )
            case "gemini_tts":
                from .sources.gemini_tts_source import (
                    ProviderGeminiTTSAPI as ProviderGeminiTTSAPI,
                )
            case "openai_embedding":
                from .sources.openai_embedding_source import (
                    OpenAIEmbeddingProvider as OpenAIEmbeddingProvider,
                )
            case "gemini_embedding":
                from .sources.gemini_embedding_source import (
                    GeminiEmbeddingProvider as GeminiEmbeddingProvider,
                )
            case "vllm_rerank":
                from .sources.vllm_rerank_source import (
                    VLLMRerankProvider as VLLMRerankProvider,
                )
            case "xinference_rerank":
                from .sources.xinference_rerank_source import (
                    XinferenceRerankProvider as XinferenceRerankProvider,
                )
            case "bailian_rerank":
                from .sources.bailian_rerank_source import (
                    BailianRerankProvider as BailianRerankProvider,
                )

    def get_merged_provider_config(self, provider_config: dict) -> dict:
        """获取 provider 配置和 provider_source 配置合并后的结果

        Returns:
            dict: 合并后的 provider 配置，key 为 provider id，value 为合并后的配置字典
        """
        pc = copy.deepcopy(provider_config)
        provider_source_id = pc.get("provider_source_id", "")
        if provider_source_id:
            provider_source = None
            for ps in self.provider_sources_config:
                if ps.get("id") == provider_source_id:
                    provider_source = ps
                    break

            if provider_source:
                # 合并配置，provider 的配置优先级更高
                merged_config = {**provider_source, **pc}
                # 保持 id 为 provider 的 id，而不是 source 的 id
                merged_config["id"] = pc["id"]
                pc = merged_config
        return pc

    def _resolve_env_key_list(self, provider_config: dict) -> dict:
        keys = provider_config.get("key", [])
        if not isinstance(keys, list):
            return provider_config
        resolved_keys = []
        for idx, key in enumerate(keys):
            if isinstance(key, str) and key.startswith("$"):
                env_key = key[1:]
                if env_key.startswith("{") and env_key.endswith("}"):
                    env_key = env_key[1:-1]
                if env_key:
                    env_val = os.getenv(env_key)
                    if env_val is None:
                        provider_id = provider_config.get("id")
                        logger.warning(
                            f"Provider {provider_id} 配置项 key[{idx}] 使用环境变量 {env_key} 但未设置。",
                        )
                        resolved_keys.append("")
                    else:
                        resolved_keys.append(env_val)
                else:
                    resolved_keys.append(key)
            else:
                resolved_keys.append(key)
        provider_config["key"] = resolved_keys
        return provider_config

    async def load_provider(self, provider_config: dict):
        # 如果 provider_source_id 存在且不为空，则从 provider_sources 中找到对应的配置并合并
        provider_config = self.get_merged_provider_config(provider_config)

        if provider_config.get("provider_type", "") == "chat_completion":
            provider_config = self._resolve_env_key_list(provider_config)

        if not provider_config["enable"]:
            logger.info(f"Provider {provider_config['id']} is disabled, skipping")
            return
        if provider_config.get("provider_type", "") == "agent_runner":
            return

        logger.info(
            f"载入 {provider_config['type']}({provider_config['id']}) 服务提供商 ...",
        )

        # 动态导入
        try:
            self.dynamic_import_provider(provider_config["type"])
        except (ImportError, ModuleNotFoundError) as e:
            logger.critical(
                f"加载 {provider_config['type']}({provider_config['id']}) 提供商适配器失败：{e}。可能是因为有未安装的依赖。",
                exc_info=True,
            )
            return
        except Exception as e:
            logger.critical(
                f"加载 {provider_config['type']}({provider_config['id']}) 提供商适配器失败：{e}。未知原因",
                exc_info=True,
            )
            return

        if provider_config["type"] not in provider_cls_map:
            logger.error(
                f"未找到适用于 {provider_config['type']}({provider_config['id']}) 的提供商适配器，请检查是否已经安装或者名称填写错误。已跳过。",
                exc_info=True,
            )
            return

        provider_metadata = provider_cls_map[provider_config["type"]]
        try:
            # 按任务实例化提供商
            cls_type = provider_metadata.cls_type
            if not cls_type:
                logger.error(f"无法找到 {provider_metadata.type} 的类")
                return

            provider_metadata.id = provider_config["id"]

            match provider_metadata.provider_type:
                case ProviderType.SPEECH_TO_TEXT:
                    # STT 任务
                    if not issubclass(cls_type, STTProvider):
                        raise TypeError(
                            f"Provider class {cls_type} is not a subclass of STTProvider"
                        )
                    inst = cls_type(provider_config, self.provider_settings)

                    if isinstance(inst, HasInitialize):
                        await inst.initialize()

                    self.stt_provider_insts.append(inst)
                    if (
                        self.provider_stt_settings.get("provider_id")
                        == provider_config["id"]
                    ):
                        self.curr_stt_provider_inst = inst
                        logger.info(
                            f"已选择 {provider_config['type']}({provider_config['id']}) 作为当前语音转文本提供商适配器。",
                        )
                    if not self.curr_stt_provider_inst:
                        self.curr_stt_provider_inst = inst

                case ProviderType.TEXT_TO_SPEECH:
                    # TTS 任务
                    if not issubclass(cls_type, TTSProvider):
                        raise TypeError(
                            f"Provider class {cls_type} is not a subclass of TTSProvider"
                        )
                    inst = cls_type(provider_config, self.provider_settings)

                    if isinstance(inst, HasInitialize):
                        await inst.initialize()

                    self.tts_provider_insts.append(inst)
                    if (
                        self.provider_settings.get("provider_id")
                        == provider_config["id"]
                    ):
                        self.curr_tts_provider_inst = inst
                        logger.info(
                            f"已选择 {provider_config['type']}({provider_config['id']}) 作为当前文本转语音提供商适配器。",
                        )
                    if not self.curr_tts_provider_inst:
                        self.curr_tts_provider_inst = inst

                case ProviderType.CHAT_COMPLETION:
                    # 文本生成任务
                    if not issubclass(cls_type, Provider):
                        raise TypeError(
                            f"Provider class {cls_type} is not a subclass of Provider"
                        )
                    inst = cls_type(
                        provider_config,
                        self.provider_settings,
                    )

                    if isinstance(inst, HasInitialize):
                        await inst.initialize()

                    self.provider_insts.append(inst)
                    if (
                        self.provider_settings.get("default_provider_id")
                        == provider_config["id"]
                    ):
                        self.curr_provider_inst = inst
                        logger.info(
                            f"已选择 {provider_config['type']}({provider_config['id']}) 作为当前提供商适配器。",
                        )
                    if not self.curr_provider_inst:
                        self.curr_provider_inst = inst

                case ProviderType.EMBEDDING:
                    if not issubclass(cls_type, EmbeddingProvider):
                        raise TypeError(
                            f"Provider class {cls_type} is not a subclass of EmbeddingProvider"
                        )
                    inst = cls_type(provider_config, self.provider_settings)
                    if isinstance(inst, HasInitialize):
                        await inst.initialize()
                    self.embedding_provider_insts.append(inst)
                case ProviderType.RERANK:
                    if not issubclass(cls_type, RerankProvider):
                        raise TypeError(
                            f"Provider class {cls_type} is not a subclass of RerankProvider"
                        )
                    inst = cls_type(provider_config, self.provider_settings)
                    if isinstance(inst, HasInitialize):
                        await inst.initialize()
                    self.rerank_provider_insts.append(inst)
                case _:
                    # 未知供应商抛出异常，确保inst初始化
                    # Should be unreachable
                    raise Exception(
                        f"未知的提供商类型：{provider_metadata.provider_type}"
                    )

            self.inst_map[provider_config["id"]] = inst
        except Exception as e:
            logger.error(
                f"实例化 {provider_config['type']}({provider_config['id']}) 提供商适配器失败：{e}",
            )
            raise Exception(
                f"实例化 {provider_config['type']}({provider_config['id']}) 提供商适配器失败：{e}",
            )

    async def reload(self, provider_config: dict):
        async with self.reload_lock:
            await self.terminate_provider(provider_config["id"])
            if provider_config["enable"]:
                await self.load_provider(provider_config)

            # 和配置文件保持同步
            self.providers_config = astrbot_config["provider"]
            self.provider_sources_config = astrbot_config.get("provider_sources", [])
            config_ids = [provider["id"] for provider in self.providers_config]
            logger.info(f"providers in user's config: {config_ids}")
            for key in list(self.inst_map.keys()):
                if key not in config_ids:
                    await self.terminate_provider(key)

            if len(self.provider_insts) == 0:
                self.curr_provider_inst = None
            elif self.curr_provider_inst is None and len(self.provider_insts) > 0:
                self.curr_provider_inst = self.provider_insts[0]
                logger.info(
                    f"自动选择 {self.curr_provider_inst.meta().id} 作为当前提供商适配器。",
                )

            if len(self.stt_provider_insts) == 0:
                self.curr_stt_provider_inst = None
            elif (
                self.curr_stt_provider_inst is None and len(self.stt_provider_insts) > 0
            ):
                self.curr_stt_provider_inst = self.stt_provider_insts[0]
                logger.info(
                    f"自动选择 {self.curr_stt_provider_inst.meta().id} 作为当前语音转文本提供商适配器。",
                )

            if len(self.tts_provider_insts) == 0:
                self.curr_tts_provider_inst = None
            elif (
                self.curr_tts_provider_inst is None and len(self.tts_provider_insts) > 0
            ):
                self.curr_tts_provider_inst = self.tts_provider_insts[0]
                logger.info(
                    f"自动选择 {self.curr_tts_provider_inst.meta().id} 作为当前文本转语音提供商适配器。",
                )

    def get_insts(self):
        return self.provider_insts

    async def terminate_provider(self, provider_id: str):
        if provider_id in self.inst_map:
            logger.info(
                f"终止 {provider_id} 提供商适配器({len(self.provider_insts)}, {len(self.stt_provider_insts)}, {len(self.tts_provider_insts)}) ...",
            )

            if self.inst_map[provider_id] in self.provider_insts:
                prov_inst = self.inst_map[provider_id]
                if isinstance(prov_inst, Provider):
                    self.provider_insts.remove(prov_inst)
            if self.inst_map[provider_id] in self.stt_provider_insts:
                prov_inst = self.inst_map[provider_id]
                if isinstance(prov_inst, STTProvider):
                    self.stt_provider_insts.remove(prov_inst)
            if self.inst_map[provider_id] in self.tts_provider_insts:
                prov_inst = self.inst_map[provider_id]
                if isinstance(prov_inst, TTSProvider):
                    self.tts_provider_insts.remove(prov_inst)

            if self.inst_map[provider_id] == self.curr_provider_inst:
                self.curr_provider_inst = None
            if self.inst_map[provider_id] == self.curr_stt_provider_inst:
                self.curr_stt_provider_inst = None
            if self.inst_map[provider_id] == self.curr_tts_provider_inst:
                self.curr_tts_provider_inst = None

            if getattr(self.inst_map[provider_id], "terminate", None):
                await self.inst_map[provider_id].terminate()  # type: ignore

            logger.info(
                f"{provider_id} 提供商适配器已终止({len(self.provider_insts)}, {len(self.stt_provider_insts)}, {len(self.tts_provider_insts)})",
            )
            del self.inst_map[provider_id]

    async def delete_provider(
        self, provider_id: str | None = None, provider_source_id: str | None = None
    ):
        """Delete provider and/or provider source from config and terminate the instances. Config will be saved after deletion."""
        async with self.resource_lock:
            # delete from config
            target_prov_ids = []
            if provider_id:
                target_prov_ids.append(provider_id)
            else:
                for prov in self.providers_config:
                    if prov.get("provider_source_id") == provider_source_id:
                        target_prov_ids.append(prov.get("id"))
            config = self.acm.default_conf
            for tpid in target_prov_ids:
                await self.terminate_provider(tpid)
                config["provider"] = [
                    prov for prov in config["provider"] if prov.get("id") != tpid
                ]
            config.save_config()
            logger.info(f"Provider {target_prov_ids} 已从配置中删除。")

    async def update_provider(self, origin_provider_id: str, new_config: dict):
        """Update provider config and reload the instance. Config will be saved after update."""
        async with self.resource_lock:
            npid = new_config.get("id", None)
            if not npid:
                raise ValueError("New provider config must have an 'id' field")
            config = self.acm.default_conf
            for provider in config["provider"]:
                if (
                    provider.get("id", None) == npid
                    and provider.get("id", None) != origin_provider_id
                ):
                    raise ValueError(f"Provider ID {npid} already exists")
            # update config
            for idx, provider in enumerate(config["provider"]):
                if provider.get("id", None) == origin_provider_id:
                    config["provider"][idx] = new_config
                    break
            else:
                raise ValueError(f"Provider ID {origin_provider_id} not found")
            config.save_config()
            # reload instance
            await self.reload(new_config)

    async def create_provider(self, new_config: dict):
        """Add new provider config and load the instance. Config will be saved after addition."""
        async with self.resource_lock:
            npid = new_config.get("id", None)
            if not npid:
                raise ValueError("New provider config must have an 'id' field")
            config = self.acm.default_conf
            for provider in config["provider"]:
                if provider.get("id", None) == npid:
                    raise ValueError(f"Provider ID {npid} already exists")
            # add to config
            config["provider"].append(new_config)
            config.save_config()
            # load instance
            await self.load_provider(new_config)

    async def terminate(self):
        for provider_inst in self.provider_insts:
            if hasattr(provider_inst, "terminate"):
                await provider_inst.terminate()  # type: ignore
        try:
            await self.llm_tools.disable_mcp_server()
        except Exception:
            logger.error("Error while disabling MCP servers", exc_info=True)
