import asyncio
import copy
import os
import traceback
from collections.abc import Callable
from importlib import import_module
from typing import Protocol, runtime_checkable

from deprecated import deprecated

from astrbot.core import astrbot_config, logger, sp
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.error_redaction import safe_error

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

# Explicit module names keep lazy imports separate from user configuration.
_PROVIDER_MODULES = {
    "openai_chat_completion": "sources.openai_source",
    "openai_responses": "sources.openai_responses_source",
    "longcat_chat_completion": "sources.longcat_source",
    "minimax_token_plan": "sources.minimax_token_plan_source",
    "xiaomi_chat_completion": "sources.xiaomi_source",
    "xiaomi_token_plan": "sources.xiaomi_token_plan_source",
    "zhipu_chat_completion": "sources.zhipu_source",
    "groq_chat_completion": "sources.groq_source",
    "xai_chat_completion": "sources.xai_source",
    "aihubmix_chat_completion": "sources.oai_aihubmix_source",
    "mirarouter_chat_completion": "sources.mirarouter_source",
    "openrouter_chat_completion": "sources.openrouter_source",
    "ssycloud_chat_completion": "sources.ssycloud_source",
    "anthropic_chat_completion": "sources.anthropic_source",
    "kimi_code_chat_completion": "sources.kimi_code_source",
    "googlegenai_chat_completion": "sources.gemini_source",
    "sensevoice_stt_selfhost": "sources.sensevoice_selfhosted_source",
    "openai_whisper_api": "sources.whisper_api_source",
    "mimo_stt_api": "sources.mimo_stt_api_source",
    "openai_whisper_selfhost": "sources.whisper_selfhosted_source",
    "xinference_stt": "sources.xinference_stt_provider",
    "openai_tts_api": "sources.openai_tts_api_source",
    "mimo_tts_api": "sources.mimo_tts_api_source",
    "genie_tts": "sources.genie_tts",
    "edge_tts": "sources.edge_tts_source",
    "gsv_tts_selfhost": "sources.gsv_selfhosted_source",
    "gsvi_tts_api": "sources.gsvi_tts_source",
    "fishaudio_tts_api": "sources.fishaudio_tts_api_source",
    "dashscope_tts": "sources.dashscope_tts",
    "azure_tts": "sources.azure_tts_source",
    "minimax_tts_api": "sources.minimax_tts_api_source",
    "volcengine_tts": "sources.volcengine_tts",
    "gemini_tts": "sources.gemini_tts_source",
    "elevenlabs_tts_api": "sources.elevenlabs_tts_source",
    "openai_embedding": "sources.openai_embedding_source",
    "gemini_embedding": "sources.gemini_embedding_source",
    "nvidia_embedding": "sources.nvidia_embedding_source",
    "ollama_embedding": "sources.ollama_embedding_source",
    "dashscope_embedding": "sources.dashscope_embedding_source",
    "vllm_rerank": "sources.vllm_rerank_source",
    "xinference_rerank": "sources.xinference_rerank_source",
    "bailian_rerank": "sources.bailian_rerank_source",
    "nvidia_rerank": "sources.nvidia_rerank_source",
    "tei_rerank": "sources.tei_rerank_source",
}

# Keep the public instance lists and legacy current-provider fields in sync.
_PROVIDER_TYPES = {
    ProviderType.CHAT_COMPLETION: (Provider, "provider_insts", "curr_provider_inst"),
    ProviderType.SPEECH_TO_TEXT: (
        STTProvider,
        "stt_provider_insts",
        "curr_stt_provider_inst",
    ),
    ProviderType.TEXT_TO_SPEECH: (
        TTSProvider,
        "tts_provider_insts",
        "curr_tts_provider_inst",
    ),
    ProviderType.EMBEDDING: (EmbeddingProvider, "embedding_provider_insts", None),
    ProviderType.RERANK: (RerankProvider, "rerank_provider_insts", None),
}


@runtime_checkable
class HasInitialize(Protocol):
    async def initialize(self) -> None: ...


class ProviderManager:
    def __init__(
        self,
        acm: AstrBotConfigManager,
        db_helper: BaseDatabase,
        persona_mgr: PersonaManager,
    ) -> None:
        self.reload_lock = asyncio.Lock()
        self.resource_lock = asyncio.Lock()
        self.persona_mgr = persona_mgr
        self.acm = acm
        config = acm.confs["default"]
        self.providers_config: list = config["provider"]
        self.provider_sources_config: list = config.get("provider_sources", [])
        self.provider_settings: dict = config["provider_settings"]
        agent_runner = config.get("agent_runner", {})
        agent_runner_config = agent_runner.get("config", {})
        self.default_chat_provider_id = (
            agent_runner_config.get("model", {}).get("provider_id", "")
            if agent_runner.get("runner_type") == "local"
            else ""
        )
        self.provider_stt_settings: dict = config.get("provider_stt_settings", {})
        self.provider_tts_settings: dict = config.get("provider_tts_settings", {})

        # 人格相关属性，v4.0.0 版本后被废弃，推荐使用 PersonaManager
        self.default_persona_name = persona_mgr.default_persona

        self.provider_insts: list[Provider] = []
        """Loaded Provider instances."""
        self.stt_provider_insts: list[STTProvider] = []
        """Loaded speech-to-text Provider instances."""
        self.tts_provider_insts: list[TTSProvider] = []
        """Loaded text-to-speech Provider instances."""
        self.embedding_provider_insts: list[EmbeddingProvider] = []
        """Loaded Embedding Provider instances."""
        self.rerank_provider_insts: list[RerankProvider] = []
        """Loaded Rerank Provider instances."""
        self.inst_map: dict[
            str,
            Providers,
        ] = {}
        """Provider instance map. Key: provider_id; value: Provider instance."""
        self.llm_tools = llm_tools

        self.curr_provider_inst: Provider | None = None
        """Default Provider instance. Deprecated; use get_using_provider()."""
        self.curr_stt_provider_inst: STTProvider | None = None
        """Default speech-to-text Provider. Deprecated; use get_using_provider()."""
        self.curr_tts_provider_inst: TTSProvider | None = None
        """Default text-to-speech Provider. Deprecated; use get_using_provider()."""
        self.db_helper = db_helper
        self._provider_change_callback: (
            Callable[[str, ProviderType, str | None], None] | None
        ) = None
        self._provider_change_hooks: list[
            Callable[[str, ProviderType, str | None], None]
        ] = []
        self._mcp_init_task: asyncio.Task | None = None

    def set_provider_change_callback(
        self,
        cb: Callable[[str, ProviderType, str | None], None] | None,
    ) -> None:
        # Backward-compatible single-callback setter.
        # This callback coexists with register_provider_change_hook subscriptions.
        self._provider_change_callback = cb

    def register_provider_change_hook(
        self,
        hook: Callable[[str, ProviderType, str | None], None],
    ) -> None:
        if hook not in self._provider_change_hooks:
            self._provider_change_hooks.append(hook)

    def _notify_provider_changed(
        self,
        provider_id: str,
        provider_type: ProviderType,
        umo: str | None,
    ) -> None:
        if self._provider_change_callback is not None:
            try:
                self._provider_change_callback(provider_id, provider_type, umo)
            except Exception as e:
                logger.warning(
                    "Provider change callback failed: provider_id=%s, type=%s, err=%s",
                    provider_id,
                    provider_type,
                    safe_error("", e),
                )
        for hook in list(self._provider_change_hooks):
            if hook is self._provider_change_callback:
                continue
            try:
                hook(provider_id, provider_type, umo)
            except Exception as e:
                logger.warning(
                    "Provider change hook failed: provider_id=%s, type=%s, err=%s",
                    provider_id,
                    provider_type,
                    safe_error("", e),
                )

    @property
    def persona_configs(self) -> list:
        """动态获取最新的 persona 配置"""
        return self.persona_mgr.persona_v3_config

    @property
    def personas(self) -> list:
        """动态获取最新的 personas 列表"""
        return self.persona_mgr.personas_v3

    @property
    @deprecated(reason="Use persona_mgr.get_default_persona_v3() instead.")
    def selected_default_persona(self):
        """动态获取最新的默认选中 persona。已弃用，请使用 context.persona_mgr.get_default_persona_v3()"""
        return self.persona_mgr.selected_default_persona_v3

    async def set_provider(
        self,
        provider_id: str,
        provider_type: ProviderType,
        umo: str | None = None,
    ) -> None:
        """设置提供商。

        Args:
            provider_id (str): 提供商 ID。
            provider_type (ProviderType): 提供商类型。
            umo (str, optional): 用户会话 ID，用于提供商会话隔离。

        Version 4.0.0: 这个版本下已经默认隔离提供商

        """
        if provider_id not in self.inst_map:
            raise ValueError(
                f"Provider {provider_id} does not exist and cannot be set."
            )
        if umo:
            await sp.session_put(
                umo,
                f"provider_perf_{provider_type.value}",
                provider_id,
            )
            self._notify_provider_changed(provider_id, provider_type, umo)
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
            self._notify_provider_changed(provider_id, provider_type, umo)
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
            self._notify_provider_changed(provider_id, provider_type, umo)
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
            self._notify_provider_changed(provider_id, provider_type, umo)

    async def get_provider_by_id(self, provider_id: str) -> Providers | None:
        """根据提供商 ID 获取提供商实例"""
        return self.inst_map.get(provider_id)

    def _resolve_using_provider(
        self,
        provider_type: ProviderType,
        umo: str | None,
        provider_id: str | None,
    ) -> Providers | None:
        """Resolve a provider preference with configuration fallbacks.

        Args:
            provider_type: Provider type to resolve.
            umo: User message origin used to load session configuration.
            provider_id: Preferred provider ID, if one is configured.

        Returns:
            Resolved provider instance, or None when the provider type is disabled
            or no provider is available.

        Raises:
            ValueError: If provider_type is unsupported.
        """
        provider = self.inst_map.get(provider_id) if provider_id else None
        if not provider:
            # default setting
            config = self.acm.get_conf(umo)
            if provider_type == ProviderType.CHAT_COMPLETION:
                agent_runner = config.get("agent_runner", {})
                provider_id = (
                    agent_runner.get("config", {}).get("model", {}).get("provider_id")
                    if agent_runner.get("runner_type") == "local"
                    else None
                )
                provider = self.inst_map.get(provider_id)
                if not provider:
                    provider = self.provider_insts[0] if self.provider_insts else None
            elif provider_type == ProviderType.SPEECH_TO_TEXT:
                provider_id = config["provider_stt_settings"].get("provider_id")
                if not config["provider_stt_settings"].get("enable"):
                    return None
                if not provider_id:
                    return None
                provider = self.inst_map.get(provider_id)
                if not provider:
                    provider = (
                        self.stt_provider_insts[0] if self.stt_provider_insts else None
                    )
            elif provider_type == ProviderType.TEXT_TO_SPEECH:
                provider_id = config["provider_tts_settings"].get("provider_id")
                if not config["provider_tts_settings"].get("enable"):
                    return None
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
                f"Provider {provider_id} was not found. Its provider or model ID "
                "may have been changed."
            )

        return provider

    @deprecated(reason="Use get_using_provider_async() instead.")
    def get_using_provider(
        self,
        provider_type: ProviderType,
        umo: str | None = None,
    ) -> Providers | None:
        """获取正在使用的提供商实例。

        Args:
            provider_type: 提供商类型。
            umo: 用户会话 ID，用于提供商会话隔离。

        Returns:
            正在使用的提供商实例。
        """
        provider_id = None
        if umo:
            provider_id = sp.get(
                f"provider_perf_{provider_type.value}",
                None,
                scope="umo",
                scope_id=umo,
            )
        return self._resolve_using_provider(provider_type, umo, provider_id)

    async def get_using_provider_async(
        self,
        provider_type: ProviderType,
        umo: str | None = None,
    ) -> Providers | None:
        """Asynchronously get the provider currently in use.

        Args:
            provider_type: Provider type to resolve.
            umo: User message origin used for session-specific preferences.

        Returns:
            Provider instance currently in use, or None if unavailable.
        """
        provider_id = None
        if umo:
            provider_id = await sp.get_async(
                "umo",
                umo,
                f"provider_perf_{provider_type.value}",
                None,
            )
        return self._resolve_using_provider(provider_type, umo, provider_id)

    async def initialize(self) -> None:
        # 逐个初始化提供商
        for provider_config in self.providers_config:
            try:
                await self.load_provider(provider_config)
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(e)

        selected_provider_id = await sp.get_async(
            key="curr_provider",
            default=self.default_chat_provider_id,
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

        async def _init_mcp_clients_bg() -> None:
            try:
                await self.llm_tools.init_mcp_clients()
            except Exception:
                logger.error("MCP init background task failed", exc_info=True)

        if self._mcp_init_task is None or self._mcp_init_task.done():
            self._mcp_init_task = asyncio.create_task(
                _init_mcp_clients_bg(),
                name="provider-manager:mcp-init",
            )

    def dynamic_import_provider(self, type: str) -> None:
        """Import a built-in adapter only when requested.

        Args:
            type: Adapter type. Plugin types are registered separately.

        Raises:
            ImportError: If a built-in adapter or its dependencies cannot load.
        """
        module = _PROVIDER_MODULES.get(type)
        if module is not None:
            import_module(f".{module}", package=__package__)

    def get_merged_provider_config(self, provider_config: dict) -> dict:
        """Merge settings without sharing mutable values between providers.

        Args:
            provider_config: Model settings, which override its source settings.

        Returns:
            Independent settings retaining the model's ID.
        """
        merged = provider_config
        source_id = provider_config.get("provider_source_id")
        if source_id:
            for source in self.provider_sources_config:
                if source.get("id") == source_id:
                    merged = {**source, **provider_config, "id": provider_config["id"]}
                    break
        return copy.deepcopy(merged)

    def get_provider_config_by_id(
        self,
        provider_id: str,
        *,
        merged: bool = False,
    ) -> dict | None:
        """Get a provider config by id.

        Args:
            provider_id: Provider id to resolve.
            merged: Whether to merge provider_source config into the provider config.
        """
        for provider_config in self.providers_config:
            if provider_config.get("id") != provider_id:
                continue
            if merged:
                return self.get_merged_provider_config(provider_config)
            return copy.deepcopy(provider_config)
        return None

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
                            f"Provider {provider_id} configuration key[{idx}] "
                            f"references environment variable {env_key}, but it is "
                            "not set.",
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

    async def load_provider(self, provider_config: dict) -> None:
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
            "Loading model %s(%s) ...",
            provider_config["type"],
            provider_config["id"],
        )

        # 动态导入
        try:
            self.dynamic_import_provider(provider_config["type"])
        except ImportError as e:
            logger.critical(
                f"Failed to load provider adapter {provider_config['type']}"
                f"({provider_config['id']}): {e}. A dependency may be missing.",
                exc_info=True,
            )
            return
        except Exception as e:
            logger.critical(
                f"Failed to load provider adapter {provider_config['type']}"
                f"({provider_config['id']}): {e}. Unknown cause.",
                exc_info=True,
            )
            return

        if provider_config["type"] not in provider_cls_map:
            logger.error(
                f"Provider adapter not found: {provider_config['type']}({provider_config['id']}). Skipped.",
                exc_info=True,
            )
            return

        provider_metadata = provider_cls_map[provider_config["type"]]
        try:
            # 按任务实例化提供商
            cls_type = provider_metadata.cls_type
            if not cls_type:
                logger.error(f"Could not find a class for {provider_metadata.type}")
                return

            provider_metadata.id = provider_config["id"]

            provider_type = provider_metadata.provider_type
            if provider_type not in _PROVIDER_TYPES:
                raise ValueError(f"Unknown provider type: {provider_type}")
            base_class, instances_attr, current_attr = _PROVIDER_TYPES[provider_type]
            if not issubclass(cls_type, base_class):
                raise TypeError(
                    f"Provider class {cls_type} is not a subclass of {base_class.__name__}"
                )
            inst = cls_type(provider_config, self.provider_settings)
            try:
                if isinstance(inst, HasInitialize):
                    await inst.initialize()
            except BaseException:
                # An unpublished instance still owns resources if initialization fails.
                if terminate := getattr(inst, "terminate", None):
                    try:
                        await terminate()
                    except Exception as e:
                        logger.error(
                            safe_error("Provider initialization cleanup failed: ", e)
                        )
                raise

            getattr(self, instances_attr).append(inst)
            if current_attr is not None:
                preferred_id = {
                    ProviderType.CHAT_COMPLETION: self.default_chat_provider_id,
                    ProviderType.SPEECH_TO_TEXT: self.provider_stt_settings.get(
                        "provider_id"
                    ),
                    ProviderType.TEXT_TO_SPEECH: self.provider_tts_settings.get(
                        "provider_id"
                    ),
                }[provider_type]
                if preferred_id == provider_config["id"]:
                    setattr(self, current_attr, inst)
                    logger.info(
                        "Selected %s(%s) as default %s provider",
                        provider_config["type"],
                        provider_config["id"],
                        provider_type.value,
                    )
                elif not getattr(self, current_attr):
                    setattr(self, current_attr, inst)

            self.inst_map[provider_config["id"]] = inst
        except Exception as e:
            logger.error(
                f"Failed to instantiate provider adapter {provider_config['type']}"
                f"({provider_config['id']}): {e}",
            )
            raise Exception(
                f"Failed to instantiate provider adapter {provider_config['type']}"
                f"({provider_config['id']}): {e}",
            )

    async def reload(self, provider_config: dict) -> None:
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

            for _, instances_attr, current_attr in _PROVIDER_TYPES.values():
                if current_attr is None:
                    continue
                instances = getattr(self, instances_attr)
                if not instances:
                    setattr(self, current_attr, None)
                elif getattr(self, current_attr) is None:
                    setattr(self, current_attr, instances[0])
                    logger.info(
                        "Automatically selected %s as %s.",
                        instances[0].meta().id,
                        current_attr,
                    )

    def get_insts(self):
        return self.provider_insts

    async def terminate_provider(self, provider_id: str) -> None:
        """Detach one instance before closing its resources.

        Args:
            provider_id: Instance to remove. Missing IDs are ignored.

        Raises:
            Exception: If the adapter fails to close, after detaching it.
        """
        inst = self.inst_map.pop(provider_id, None)
        if inst is None:
            return
        # Detach before awaiting: failure or cancellation must not leave a stale
        # instance, and a replacement registered during close must remain intact.
        for _, instances_attr, current_attr in _PROVIDER_TYPES.values():
            instances = getattr(self, instances_attr)
            instances[:] = [item for item in instances if item is not inst]
            if current_attr is not None and getattr(self, current_attr) is inst:
                setattr(self, current_attr, None)
        logger.info("Terminating provider adapter %s ...", provider_id)
        if terminate := getattr(inst, "terminate", None):
            await terminate()
        logger.info("Provider adapter %s terminated", provider_id)

    async def delete_provider(
        self, provider_id: str | None = None, provider_source_id: str | None = None
    ) -> None:
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
            # sync in-memory config for API queries (e.g., provider list)
            self.providers_config = config["provider"]
            logger.info(f"Providers {target_prov_ids} were removed from configuration.")

    async def update_provider(self, origin_provider_id: str, new_config: dict) -> None:
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

    async def create_provider(self, new_config: dict) -> None:
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
            # sync in-memory config for API queries (e.g., embedding provider list)
            self.providers_config = astrbot_config["provider"]

    async def terminate(self) -> None:
        if self._mcp_init_task and not self._mcp_init_task.done():
            self._mcp_init_task.cancel()
            try:
                await self._mcp_init_task
            except asyncio.CancelledError:
                pass

        for provider_id in list(self.inst_map):
            try:
                await self.terminate_provider(provider_id)
            except Exception as e:
                logger.error(
                    safe_error(f"Failed to terminate provider {provider_id}: ", e)
                )
        try:
            await self.llm_tools.disable_mcp_server()
        except Exception:
            logger.error("Error while disabling MCP servers", exc_info=True)
