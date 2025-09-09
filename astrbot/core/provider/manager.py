import asyncio
import traceback
from typing import List

from astrbot.core import logger, sp
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.db import BaseDatabase

from .entities import ProviderType
from .provider import Provider, STTProvider, TTSProvider, EmbeddingProvider
from .register import llm_tools, provider_cls_map
from ..persona_mgr import PersonaManager


class ProviderManager:
    def __init__(
        self,
        acm: AstrBotConfigManager,
        db_helper: BaseDatabase,
        persona_mgr: PersonaManager,
    ):
        self.persona_mgr = persona_mgr
        self.acm = acm
        config = acm.confs["default"]
        self.providers_config: List = config["provider"]
        self.provider_settings: dict = config["provider_settings"]
        self.provider_stt_settings: dict = config.get("provider_stt_settings", {})
        self.provider_tts_settings: dict = config.get("provider_tts_settings", {})

        # 人格相关属性，v4.0.0 版本后被废弃，推荐使用 PersonaManager
        self.default_persona_name = persona_mgr.default_persona

        self.provider_insts: List[Provider] = []
        """加载的 Provider 的实例"""
        self.stt_provider_insts: List[STTProvider] = []
        """加载的 Speech To Text Provider 的实例"""
        self.tts_provider_insts: List[TTSProvider] = []
        """加载的 Text To Speech Provider 的实例"""
        self.embedding_provider_insts: List[EmbeddingProvider] = []
        """加载的 Embedding Provider 的实例"""
        self.inst_map: dict[str, Provider] = {}
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
        self, provider_id: str, provider_type: ProviderType, umo: str | None = None
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
        self.curr_provider_inst = self.inst_map[provider_id]
        if provider_type == ProviderType.TEXT_TO_SPEECH:
            sp.put("curr_provider_tts", provider_id, scope="global", scope_id="global")
        elif provider_type == ProviderType.SPEECH_TO_TEXT:
            sp.put("curr_provider_stt", provider_id, scope="global", scope_id="global")
        elif provider_type == ProviderType.CHAT_COMPLETION:
            sp.put("curr_provider", provider_id, scope="global", scope_id="global")

    async def get_provider_by_id(self, provider_id: str) -> Provider | None:
        """根据提供商 ID 获取提供商实例"""
        return self.inst_map.get(provider_id)

    def get_using_provider(self, provider_type: ProviderType, umo=None):
        """获取正在使用的提供商实例。

        Args:
            provider_type (ProviderType): 提供商类型。
            umo (str, optional): 用户会话 ID，用于提供商会话隔离。

        Returns:
            Provider: 正在使用的提供商实例。
        """
        provider = None
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
        return provider

    async def initialize(self):
        # 逐个初始化提供商
        for provider_config in self.providers_config:
            await self.load_provider(provider_config)

        # 设置默认提供商
        selected_provider_id = sp.get(
            "curr_provider",
            self.provider_settings.get("default_provider_id"),
            scope="global",
            scope_id="global",
        )
        selected_stt_provider_id = sp.get(
            "curr_provider_stt",
            self.provider_stt_settings.get("provider_id"),
            scope="global",
            scope_id="global",
        )
        selected_tts_provider_id = sp.get(
            "curr_provider_tts",
            self.provider_tts_settings.get("provider_id"),
            scope="global",
            scope_id="global",
        )
        self.curr_provider_inst = self.inst_map.get(selected_provider_id)
        if not self.curr_provider_inst and self.provider_insts:
            self.curr_provider_inst = self.provider_insts[0]

        self.curr_stt_provider_inst = self.inst_map.get(selected_stt_provider_id)
        if not self.curr_stt_provider_inst and self.stt_provider_insts:
            self.curr_stt_provider_inst = self.stt_provider_insts[0]

        self.curr_tts_provider_inst = self.inst_map.get(selected_tts_provider_id)
        if not self.curr_tts_provider_inst and self.tts_provider_insts:
            self.curr_tts_provider_inst = self.tts_provider_insts[0]

        # 初始化 MCP Client 连接
        asyncio.create_task(self.llm_tools.init_mcp_clients(), name="init_mcp_clients")

    async def load_provider(self, provider_config: dict):
        if not provider_config["enable"]:
            return

        logger.info(
            f"载入 {provider_config['type']}({provider_config['id']}) 服务提供商 ..."
        )

        # 动态导入
        try:
            match provider_config["type"]:
                case "openai_chat_completion":
                    from .sources.openai_source import (
                        ProviderOpenAIOfficial as ProviderOpenAIOfficial,
                    )
                case "zhipu_chat_completion":
                    from .sources.zhipu_source import ProviderZhipu as ProviderZhipu
                case "anthropic_chat_completion":
                    from .sources.anthropic_source import (
                        ProviderAnthropic as ProviderAnthropic,
                    )
                case "dify":
                    from .sources.dify_source import ProviderDify as ProviderDify
                case "dashscope":
                    from .sources.dashscope_source import (
                        ProviderDashscope as ProviderDashscope,
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
                case "openai_tts_api":
                    from .sources.openai_tts_api_source import (
                        ProviderOpenAITTSAPI as ProviderOpenAITTSAPI,
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
        except (ImportError, ModuleNotFoundError) as e:
            logger.critical(
                f"加载 {provider_config['type']}({provider_config['id']}) 提供商适配器失败：{e}。可能是因为有未安装的依赖。"
            )
            return
        except Exception as e:
            logger.critical(
                f"加载 {provider_config['type']}({provider_config['id']}) 提供商适配器失败：{e}。未知原因"
            )
            return

        if provider_config["type"] not in provider_cls_map:
            logger.error(
                f"未找到适用于 {provider_config['type']}({provider_config['id']}) 的提供商适配器，请检查是否已经安装或者名称填写错误。已跳过。"
            )
            return

        provider_metadata = provider_cls_map[provider_config["type"]]
        try:
            # 按任务实例化提供商

            if provider_metadata.provider_type == ProviderType.SPEECH_TO_TEXT:
                # STT 任务
                inst = provider_metadata.cls_type(
                    provider_config, self.provider_settings
                )

                if getattr(inst, "initialize", None):
                    await inst.initialize()

                self.stt_provider_insts.append(inst)
                if (
                    self.provider_stt_settings.get("provider_id")
                    == provider_config["id"]
                ):
                    self.curr_stt_provider_inst = inst
                    logger.info(
                        f"已选择 {provider_config['type']}({provider_config['id']}) 作为当前语音转文本提供商适配器。"
                    )
                if not self.curr_stt_provider_inst:
                    self.curr_stt_provider_inst = inst

            elif provider_metadata.provider_type == ProviderType.TEXT_TO_SPEECH:
                # TTS 任务
                inst = provider_metadata.cls_type(
                    provider_config, self.provider_settings
                )

                if getattr(inst, "initialize", None):
                    await inst.initialize()

                self.tts_provider_insts.append(inst)
                if self.provider_settings.get("provider_id") == provider_config["id"]:
                    self.curr_tts_provider_inst = inst
                    logger.info(
                        f"已选择 {provider_config['type']}({provider_config['id']}) 作为当前文本转语音提供商适配器。"
                    )
                if not self.curr_tts_provider_inst:
                    self.curr_tts_provider_inst = inst

            elif provider_metadata.provider_type == ProviderType.CHAT_COMPLETION:
                # 文本生成任务
                inst = provider_metadata.cls_type(
                    provider_config,
                    self.provider_settings,
                    self.selected_default_persona,
                )

                if getattr(inst, "initialize", None):
                    await inst.initialize()

                self.provider_insts.append(inst)
                if (
                    self.provider_settings.get("default_provider_id")
                    == provider_config["id"]
                ):
                    self.curr_provider_inst = inst
                    logger.info(
                        f"已选择 {provider_config['type']}({provider_config['id']}) 作为当前提供商适配器。"
                    )
                if not self.curr_provider_inst:
                    self.curr_provider_inst = inst

            elif provider_metadata.provider_type in [ProviderType.EMBEDDING, ProviderType.RERANK]:
                inst = provider_metadata.cls_type(
                    provider_config, self.provider_settings
                )
                if getattr(inst, "initialize", None):
                    await inst.initialize()
                self.embedding_provider_insts.append(inst)

            self.inst_map[provider_config["id"]] = inst
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(
                f"实例化 {provider_config['type']}({provider_config['id']}) 提供商适配器失败：{e}"
            )

    async def reload(self, provider_config: dict):
        await self.terminate_provider(provider_config["id"])
        if provider_config["enable"]:
            await self.load_provider(provider_config)

        # 和配置文件保持同步
        config_ids = [provider["id"] for provider in self.providers_config]
        for key in list(self.inst_map.keys()):
            if key not in config_ids:
                await self.terminate_provider(key)

        if len(self.provider_insts) == 0:
            self.curr_provider_inst = None
        elif self.curr_provider_inst is None and len(self.provider_insts) > 0:
            self.curr_provider_inst = self.provider_insts[0]
            logger.info(
                f"自动选择 {self.curr_provider_inst.meta().id} 作为当前提供商适配器。"
            )

        if len(self.stt_provider_insts) == 0:
            self.curr_stt_provider_inst = None
        elif self.curr_stt_provider_inst is None and len(self.stt_provider_insts) > 0:
            self.curr_stt_provider_inst = self.stt_provider_insts[0]
            logger.info(
                f"自动选择 {self.curr_stt_provider_inst.meta().id} 作为当前语音转文本提供商适配器。"
            )

        if len(self.tts_provider_insts) == 0:
            self.curr_tts_provider_inst = None
        elif self.curr_tts_provider_inst is None and len(self.tts_provider_insts) > 0:
            self.curr_tts_provider_inst = self.tts_provider_insts[0]
            logger.info(
                f"自动选择 {self.curr_tts_provider_inst.meta().id} 作为当前文本转语音提供商适配器。"
            )

    def get_insts(self):
        return self.provider_insts

    async def terminate_provider(self, provider_id: str):
        if provider_id in self.inst_map:
            logger.info(
                f"终止 {provider_id} 提供商适配器({len(self.provider_insts)}, {len(self.stt_provider_insts)}, {len(self.tts_provider_insts)}) ..."
            )

            if self.inst_map[provider_id] in self.provider_insts:
                self.provider_insts.remove(self.inst_map[provider_id])
            if self.inst_map[provider_id] in self.stt_provider_insts:
                self.stt_provider_insts.remove(self.inst_map[provider_id])
            if self.inst_map[provider_id] in self.tts_provider_insts:
                self.tts_provider_insts.remove(self.inst_map[provider_id])

            if self.inst_map[provider_id] == self.curr_provider_inst:
                self.curr_provider_inst = None
            if self.inst_map[provider_id] == self.curr_stt_provider_inst:
                self.curr_stt_provider_inst = None
            if self.inst_map[provider_id] == self.curr_tts_provider_inst:
                self.curr_tts_provider_inst = None

            if getattr(self.inst_map[provider_id], "terminate", None):
                await self.inst_map[provider_id].terminate()  # type: ignore

            logger.info(
                f"{provider_id} 提供商适配器已终止({len(self.provider_insts)}, {len(self.stt_provider_insts)}, {len(self.tts_provider_insts)})"
            )
            del self.inst_map[provider_id]

    async def terminate(self):
        for provider_inst in self.provider_insts:
            if hasattr(provider_inst, "terminate"):
                await provider_inst.terminate()  # type: ignore
        try:
            await self.llm_tools.disable_mcp_server()
        except Exception:
            logger.error("Error while disabling MCP servers", exc_info=True)
