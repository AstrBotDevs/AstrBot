import asyncio
import copy
import importlib
import os
import traceback
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from astrbot import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.tools.function_tool_manager import FunctionToolManager
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.shared_preferences import SharedPreferences

from ..persona_mgr import PersonaManager
from .catalog import ProviderAdapterDescriptor, ProviderCatalog
from .entities import ProviderType
from .provider import (
    EmbeddingProvider,
    Provider,
    Providers,
    RerankProvider,
    STTProvider,
    TTSProvider,
)
from .provider_modules import PROVIDER_MODULES


@runtime_checkable
class HasInitialize(Protocol):
    async def initialize(self) -> None: ...


class ProviderManager:
    def __init__(
        self,
        acm: AstrBotConfigManager,
        persona_mgr: PersonaManager,
        preferences: SharedPreferences,
        catalog: ProviderCatalog,
        tools: FunctionToolManager,
    ) -> None:
        self.reload_lock = asyncio.Lock()
        self.resource_lock = asyncio.Lock()
        self.persona_mgr = persona_mgr
        self.acm = acm
        self.catalog = catalog
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

        # Kept only because some runtime code still reads the current default persona name directly.
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
        self.tool_manager = tools
        self.tool_manager.bind_preferences(preferences)

        self.preferences = preferences
        self._provider_change_hooks: list[
            Callable[[str, ProviderType, str | None], None]
        ] = []
        self._mcp_init_task: asyncio.Task | None = None
        self._session_provider_overrides: dict[str, dict[ProviderType, str]] = {}

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
        for hook in list(self._provider_change_hooks):
            try:
                hook(provider_id, provider_type, umo)
            except Exception as e:
                logger.warning(
                    "调用 provider 变更钩子失败: provider_id=%s, type=%s, err=%s",
                    provider_id,
                    provider_type,
                    safe_error("", e),
                )

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
            raise ValueError(f"提供商 {provider_id} 不存在，无法设置。")
        if umo:
            await self.preferences.session_put(
                umo,
                f"provider_perf_{provider_type.value}",
                provider_id,
            )
            self._session_provider_overrides.setdefault(umo, {})[provider_type] = (
                provider_id
            )
            self._notify_provider_changed(provider_id, provider_type, umo)
            return

        async with self.resource_lock:
            # Global selection belongs to the active default configuration, not a
            # runtime cache or a second preference-backed source of truth.
            prov = self.inst_map.get(provider_id)
            if prov is None:
                raise ValueError(f"提供商 {provider_id} 不存在，无法设置。")

            settings_key: str | None = None
            selection: dict[str, object] = {}
            if provider_type == ProviderType.TEXT_TO_SPEECH and isinstance(
                prov,
                TTSProvider,
            ):
                settings_key = "provider_tts_settings"
                selection = {"provider_id": provider_id, "enable": True}
            elif provider_type == ProviderType.SPEECH_TO_TEXT and isinstance(
                prov,
                STTProvider,
            ):
                settings_key = "provider_stt_settings"
                selection = {"provider_id": provider_id, "enable": True}
            elif provider_type == ProviderType.CHAT_COMPLETION and isinstance(
                prov,
                Provider,
            ):
                config = self.acm.default_conf
                next_config = copy.deepcopy(dict(config))
                agent_runner = next_config.setdefault("agent_runner", {})
                if agent_runner.get("runner_type", "local") != "local":
                    return
                runner_config = agent_runner.setdefault("config", {})
                model_config = runner_config.setdefault("model", {})
                model_config["provider_id"] = provider_id
                previous = copy.deepcopy(dict(config))
                config.clear()
                config.update(next_config)
                expected = copy.deepcopy(next_config)
                try:
                    committed = await config.save_config_async()
                    if not committed:
                        raise RuntimeError(
                            "Provider selection was superseded by a newer configuration write."
                        )
                except BaseException:
                    if dict(config) == expected:
                        config.clear()
                        config.update(previous)
                    raise
                self.default_chat_provider_id = provider_id
                self._notify_provider_changed(provider_id, provider_type, umo)
                return

            if settings_key is None:
                return

            config = self.acm.default_conf
            next_config = copy.deepcopy(dict(config))
            next_settings = next_config[settings_key]
            next_settings.update(selection)
            settings = config[settings_key]
            previous_settings = copy.deepcopy(settings)
            settings.clear()
            settings.update(next_settings)
            try:
                committed = await config.save_config_async()
                if not committed:
                    raise RuntimeError(
                        "Provider selection was superseded by a newer configuration write."
                    )
            except BaseException:
                # A concurrent selection may have updated the same nested
                # mapping while this snapshot was being written. Restore only
                # the value still owned by this operation.
                if settings == next_settings:
                    settings.clear()
                    settings.update(previous_settings)
                raise

            self._notify_provider_changed(provider_id, provider_type, umo)

    async def get_provider_by_id(self, provider_id: str) -> Providers | None:
        """根据提供商 ID 获取提供商实例"""
        return self.inst_map.get(provider_id)

    @staticmethod
    def _provider_pref_key(provider_type: ProviderType) -> str:
        return f"provider_perf_{provider_type.value}"

    async def _persist_provider_configs(self, provider_configs: list[dict]) -> None:
        """Persist a complete provider list before changing live adapters.

        The manager retains its previous list while the write is in progress, so
        callers cannot reload or terminate providers after a failed save.
        """

        config = self.acm.default_conf
        previous_provider_configs = config["provider"]
        config["provider"] = provider_configs
        try:
            committed = await config.save_config_async()
            if not committed:
                raise RuntimeError(
                    "Provider configuration write was superseded by a newer revision."
                )
        except BaseException:
            # A concurrent config operation may have installed a newer list while
            # this write was in flight. Only restore the list still owned by this
            # operation; never clobber that newer in-memory state.
            if config.get("provider") is provider_configs:
                config["provider"] = previous_provider_configs
            raise

    async def _load_session_provider_overrides(self) -> None:
        overrides: dict[str, dict[ProviderType, str]] = {}
        prefs = await self.preferences.session_get(None, None)
        for pref in prefs:
            key = pref.key
            if not isinstance(key, str) or not key.startswith("provider_perf_"):
                continue
            provider_value = (
                pref.value.get("val") if isinstance(pref.value, dict) else None
            )
            if not isinstance(provider_value, str) or not provider_value:
                continue
            provider_type_value = key.removeprefix("provider_perf_")
            try:
                provider_type = ProviderType(provider_type_value)
            except ValueError:
                continue
            overrides.setdefault(pref.scope_id, {})[provider_type] = provider_value
        self._session_provider_overrides = overrides

    async def clear_provider_override(
        self,
        umo: str,
        provider_type: ProviderType,
    ) -> None:
        provider_overrides = self._session_provider_overrides.get(umo)
        if provider_overrides is not None:
            provider_overrides.pop(provider_type, None)
            if not provider_overrides:
                self._session_provider_overrides.pop(umo, None)
        await self.preferences.session_remove(
            umo, self._provider_pref_key(provider_type)
        )

    async def clear_all_provider_overrides(self, umo: str) -> None:
        overrides = self._session_provider_overrides.pop(umo, {})
        for provider_type in list(overrides):
            await self.preferences.session_remove(
                umo, self._provider_pref_key(provider_type)
            )

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
            provider_id = self._session_provider_overrides.get(umo, {}).get(
                provider_type
            )
            if provider_id:
                provider = self.inst_map.get(provider_id)
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
                if isinstance(provider_id, str) and provider_id:
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
                f"没有找到 ID 为 {provider_id} 的提供商，这可能是由于您修改了提供商（模型）ID 导致的。"
            )

        return provider

    async def initialize(self) -> None:
        await self._load_session_provider_overrides()
        # 逐个初始化提供商
        for provider_config in self.providers_config:
            try:
                await self.load_provider(provider_config)
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(e)

        async def _init_mcp_clients_bg() -> None:
            try:
                await self.tool_manager.init_mcp_clients()
            except Exception:
                logger.error("MCP init background task failed", exc_info=True)

        if self._mcp_init_task is None or self._mcp_init_task.done():
            self._mcp_init_task = asyncio.create_task(
                _init_mcp_clients_bg(),
                name="provider-manager:mcp-init",
            )

    def dynamic_import_provider(self, provider_type: str) -> None:
        """动态导入提供商适配器模块

        Args:
            provider_type: 提供商请求类型。

        Raises:
            ImportError: 如果提供商类型未知或无法导入对应模块，则抛出异常。
        """
        module_name = PROVIDER_MODULES.get(provider_type)
        if module_name is not None:
            module = importlib.import_module(module_name)
            self.catalog.register_module(module)

    @staticmethod
    def _bind_adapter_descriptor(
        provider: object,
        descriptor: ProviderAdapterDescriptor,
    ) -> None:
        """Bind catalog metadata to instances without a class declaration."""

        setattr(provider, "_provider_adapter_descriptor", descriptor)

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

        registration = self.catalog.get(provider_config["type"])
        if registration is None:
            logger.error(
                f"Provider adapter not found: {provider_config['type']}({provider_config['id']}). Skipped.",
                exc_info=True,
            )
            return

        provider_metadata = registration.descriptor
        try:
            # 按任务实例化提供商
            cls_type = registration.cls_type
            if not cls_type:
                logger.error(f"无法找到 {provider_metadata.type} 的类")
                return

            match provider_metadata.provider_type:
                case ProviderType.SPEECH_TO_TEXT:
                    # STT 任务
                    if not issubclass(cls_type, STTProvider):
                        raise TypeError(
                            f"Provider class {cls_type} is not a subclass of STTProvider"
                        )
                    inst = cls_type(provider_config, self.provider_settings)
                    self._bind_adapter_descriptor(inst, provider_metadata)

                    if isinstance(inst, HasInitialize):
                        await inst.initialize()

                    self.stt_provider_insts.append(inst)

                case ProviderType.TEXT_TO_SPEECH:
                    # TTS 任务
                    if not issubclass(cls_type, TTSProvider):
                        raise TypeError(
                            f"Provider class {cls_type} is not a subclass of TTSProvider"
                        )
                    inst = cls_type(provider_config, self.provider_settings)
                    self._bind_adapter_descriptor(inst, provider_metadata)

                    if isinstance(inst, HasInitialize):
                        await inst.initialize()

                    self.tts_provider_insts.append(inst)

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
                    self._bind_adapter_descriptor(inst, provider_metadata)

                    if isinstance(inst, HasInitialize):
                        await inst.initialize()

                    self.provider_insts.append(inst)

                case ProviderType.EMBEDDING:
                    if not issubclass(cls_type, EmbeddingProvider):
                        raise TypeError(
                            f"Provider class {cls_type} is not a subclass of EmbeddingProvider"
                        )
                    inst = cls_type(provider_config, self.provider_settings)
                    self._bind_adapter_descriptor(inst, provider_metadata)
                    if isinstance(inst, HasInitialize):
                        await inst.initialize()
                    self.embedding_provider_insts.append(inst)
                case ProviderType.RERANK:
                    if not issubclass(cls_type, RerankProvider):
                        raise TypeError(
                            f"Provider class {cls_type} is not a subclass of RerankProvider"
                        )
                    inst = cls_type(provider_config, self.provider_settings)
                    self._bind_adapter_descriptor(inst, provider_metadata)
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

    async def reload(self, provider_config: dict) -> None:
        async with self.reload_lock:
            await self.terminate_provider(provider_config["id"])
            if provider_config["enable"]:
                await self.load_provider(provider_config)

            # 和配置文件保持同步
            self.providers_config = self.acm.default_conf["provider"]
            self.provider_sources_config = self.acm.default_conf.get(
                "provider_sources", []
            )
            config_ids = [provider["id"] for provider in self.providers_config]
            logger.info(f"providers in user's config: {config_ids}")
            for key in list(self.inst_map.keys()):
                if key not in config_ids:
                    await self.terminate_provider(key)

    def get_insts(self):
        return self.provider_insts

    async def terminate_provider(self, provider_id: str) -> None:
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
            if self.inst_map[provider_id] in self.embedding_provider_insts:
                prov_inst = self.inst_map[provider_id]
                if isinstance(prov_inst, EmbeddingProvider):
                    self.embedding_provider_insts.remove(prov_inst)
            if self.inst_map[provider_id] in self.rerank_provider_insts:
                prov_inst = self.inst_map[provider_id]
                if isinstance(prov_inst, RerankProvider):
                    self.rerank_provider_insts.remove(prov_inst)

            if getattr(self.inst_map[provider_id], "terminate", None):
                await self.inst_map[provider_id].terminate()  # type: ignore

            logger.info(
                f"{provider_id} 提供商适配器已终止({len(self.provider_insts)}, {len(self.stt_provider_insts)}, {len(self.tts_provider_insts)})",
            )
            del self.inst_map[provider_id]

    async def delete_provider(
        self, provider_id: str | None = None, provider_source_id: str | None = None
    ) -> None:
        """Delete provider and/or provider source from config and terminate the instances. Config will be saved after deletion."""
        async with self.resource_lock:
            target_prov_ids: list[str] = []
            if provider_id:
                target_prov_ids.append(provider_id)
            else:
                for prov in self.providers_config:
                    target_id = prov.get("id")
                    if prov.get(
                        "provider_source_id"
                    ) == provider_source_id and isinstance(target_id, str):
                        target_prov_ids.append(target_id)
            config = self.acm.default_conf
            new_provider_configs = [
                prov
                for prov in config["provider"]
                if prov.get("id") not in target_prov_ids
            ]
            await self._persist_provider_configs(new_provider_configs)
            self.providers_config = config["provider"]

            for tpid in target_prov_ids:
                await self.terminate_provider(tpid)
            logger.info(f"Provider {target_prov_ids} 已从配置中删除。")

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
            if not any(
                provider.get("id", None) == origin_provider_id
                for provider in config["provider"]
            ):
                raise ValueError(f"Provider ID {origin_provider_id} not found")
            new_provider_configs = [
                (
                    new_config
                    if provider.get("id", None) == origin_provider_id
                    else provider
                )
                for provider in config["provider"]
            ]
            await self._persist_provider_configs(new_provider_configs)
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
            new_provider_configs = [*config["provider"], new_config]
            await self._persist_provider_configs(new_provider_configs)
            await self.load_provider(new_config)
            self.providers_config = self.acm.default_conf["provider"]

    async def terminate(self) -> None:
        if self._mcp_init_task and not self._mcp_init_task.done():
            self._mcp_init_task.cancel()
            try:
                await self._mcp_init_task
            except asyncio.CancelledError:
                pass

        provider_groups = (
            self.provider_insts,
            self.stt_provider_insts,
            self.tts_provider_insts,
            self.embedding_provider_insts,
            self.rerank_provider_insts,
        )
        terminated_ids: set[int] = set()
        for provider_group in provider_groups:
            for provider_inst in provider_group:
                if id(provider_inst) in terminated_ids:
                    continue
                terminated_ids.add(id(provider_inst))
                if hasattr(provider_inst, "terminate"):
                    await provider_inst.terminate()  # type: ignore
        try:
            await self.tool_manager.disable_mcp_server()
        except Exception:
            logger.error("Error while disabling MCP servers", exc_info=True)
