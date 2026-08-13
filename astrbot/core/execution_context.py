import asyncio
import logging
from asyncio import Queue, QueueFull
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol

from astrbot.core.agent.follow_up import FollowUpCoordinator
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.llm_types import LLMResponse, ProviderRequest
from astrbot.core.agent.message import Message
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent.tool_image_cache import ToolImageCache
from astrbot.core.assistant_history import AssistantHistoryCommitter
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.auth.service import AuthorizationService
from astrbot.core.computer.computer_client import ComputerRuntime
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.protocols import PluginRuntimeStore
from astrbot.core.exceptions import ProviderNotFoundError
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.platform.astr_message_event import AstrMessageEvent, MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.send_result import DeliveryReceipt, PlatformSendResult
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.provider import (
    EmbeddingProvider,
    Provider,
    RerankProvider,
    STTProvider,
    TTSProvider,
)
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.dashboard_extension import (
    DashboardExtensionAccess,
    DashboardExtensionRegistry,
)
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata
from astrbot.core.subagent_orchestrator import SubAgentOrchestrator
from astrbot.core.tools.function_tool_manager import FunctionToolManager
from astrbot.core.utils.active_event_registry import ActiveEventRegistry
from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path
from astrbot.core.utils.llm_metadata import LLMMetadataCatalog
from astrbot.core.utils.metrics import MetricsSink
from astrbot.core.utils.session_lock import SessionLockManager
from astrbot.core.utils.session_waiter import SessionWaiterRegistry

logger = logging.getLogger("astrbot")

if TYPE_CHECKING:
    from astrbot.core.cron.manager import CronJobManager
    from astrbot.core.file_token_service import FileTokenService
    from astrbot.core.memory import MemoryManager
    from astrbot.core.persona_runtime import PersonaRuntimeManager
    from astrbot.core.skills.skill_manager import SkillManager
    from astrbot.core.utils.shared_preferences import SharedPreferences
    from astrbot.core.utils.t2i.renderer import HtmlRenderer

_PLUGIN_MODULE_FLAGS = {"builtin_stars", "plugins"}


def _split_module_path(module_path: Any) -> list[str]:
    if not isinstance(module_path, str) or not module_path:
        return []
    return module_path.split(".")


def _plugin_root_from_module_parts(parts: list[str]) -> tuple[str, str] | None:
    for index, part in enumerate(parts):
        if part in _PLUGIN_MODULE_FLAGS and index + 1 < len(parts):
            return part, parts[index + 1]
    return None


def _plugin_root_from_metadata(metadata: StarMetadata) -> str | None:
    if metadata.root_dir_name:
        return metadata.root_dir_name

    root_info = _plugin_root_from_module_parts(_split_module_path(metadata.module_path))
    return root_info[1] if root_info else None


def _registered_plugin_module_path(
    catalogs: RuntimeCatalogs,
    root_dir_name: str,
    flag: str | None,
) -> str | None:
    for metadata in reversed(catalogs.plugins.all()):
        if not metadata.module_path:
            continue
        if _plugin_root_from_metadata(metadata) != root_dir_name:
            continue
        if flag and flag not in _split_module_path(metadata.module_path):
            continue
        return metadata.module_path
    return None


def _resolve_tool_handler_module_path(
    catalogs: RuntimeCatalogs,
    tool: FunctionTool,
) -> str:
    module_path = getattr(tool, "__module__", None)
    module_parts = _split_module_path(module_path)
    if not module_parts:
        return module_path if isinstance(module_path, str) else ""

    root_info = _plugin_root_from_module_parts(module_parts)
    if root_info:
        flag, root_dir_name = root_info
        registered_module_path = _registered_plugin_module_path(
            catalogs,
            root_dir_name,
            flag,
        )
        return registered_module_path or ".".join(module_parts)

    registered_module_path = _registered_plugin_module_path(
        catalogs,
        module_parts[0],
        "plugins",
    )
    return registered_module_path or ".".join(module_parts)


class PlatformManagerProtocol(Protocol):
    def create_event(
        self,
        platform: str,
        event_message: object,
        *,
        is_wake: bool = True,
    ) -> None: ...

    async def invoke_action(
        self,
        platform_id: str,
        action_name: str,
        **kwargs,
    ) -> dict[str, object]: ...

    async def invoke_capability(
        self,
        platform_id: str,
        capability_name: str,
        action_name: str,
        **kwargs,
    ) -> object: ...

    def get_platform_capabilities(self, platform_id: str) -> tuple[object, ...]: ...

    async def refresh_registered_commands(self) -> None: ...

    async def send_to_session(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ) -> PlatformSendResult: ...


class CoreExecutionContext:
    """Runtime-owned execution dependencies used by core services."""

    def __init__(
        self,
        event_queue: Queue,
        config: AstrBotConfig,
        db: PluginRuntimeStore,
        provider_manager: ProviderManager,
        platform_manager: PlatformManagerProtocol,
        conversation_manager: ConversationManager,
        message_history_manager: PlatformMessageHistoryManager,
        persona_manager: PersonaManager,
        astrbot_config_mgr: AstrBotConfigManager,
        knowledge_base_manager: KnowledgeBaseManager,
        cron_manager: CronJobManager,
        preferences: SharedPreferences,
        html_renderer: HtmlRenderer,
        file_token_service: FileTokenService,
        catalogs: RuntimeCatalogs,
        computer_runtime: ComputerRuntime,
        tool_image_cache: ToolImageCache,
        subagent_orchestrator: SubAgentOrchestrator | None = None,
        demo_mode: bool = False,
        *,
        metrics: MetricsSink,
        active_event_registry: ActiveEventRegistry | None = None,
        session_lock_manager: SessionLockManager | None = None,
        session_waiter_registry: SessionWaiterRegistry | None = None,
        follow_up_coordinator: FollowUpCoordinator | None = None,
        llm_metadata_catalog: LLMMetadataCatalog | None = None,
        authorization: AuthorizationService | None = None,
    ) -> None:
        self._event_queue = event_queue
        """事件队列。消息平台通过事件队列传递消息事件。"""
        self._config = config
        """AstrBot 默认配置"""
        self.database = db
        """Narrow persistence capabilities used by core plugin execution."""
        self.provider_manager = provider_manager
        """模型提供商管理器"""
        self._platform_manager = platform_manager
        """平台适配器管理器"""
        self.conversation_manager = conversation_manager
        """会话管理器"""
        self.message_history_manager = message_history_manager
        """平台消息历史管理器"""
        self.persona_manager = persona_manager
        """人格角色设定管理器"""
        self.astrbot_config_mgr = astrbot_config_mgr
        """配置文件管理器(非webui)"""
        self.kb_manager = knowledge_base_manager
        """知识库管理器"""
        self.cron_manager = cron_manager
        """Cron job manager, initialized by core lifecycle."""
        self.preferences = preferences
        """Persistent preferences available to plugins."""
        self.html_renderer = html_renderer
        """HTML-to-image capability available to plugins."""
        self.file_token_service = file_token_service
        """Temporary file publication capability available to plugins."""
        self.catalogs = catalogs
        """Runtime-owned plugin, handler, and function-tool catalogs."""
        self.authorization = authorization
        """Runtime-owned action/resource authorization service."""
        self.llm_metadata_catalog = llm_metadata_catalog or LLMMetadataCatalog()
        """Runtime-owned model metadata used by Agent and Dashboard paths."""
        self.metrics = metrics
        """Runtime-owned telemetry capability used by Agent execution."""
        self.follow_up_coordinator = follow_up_coordinator or FollowUpCoordinator()
        """Runtime-owned active Agent follow-up coordination state."""
        self.background_tasks: set[asyncio.Task] = set()
        """Auxiliary Agent tasks cancelled with this runtime."""
        self.assistant_history_committer = AssistantHistoryCommitter()
        """Serializes accepted assistant-history projections per conversation."""
        self.computer_runtime = computer_runtime
        """Runtime-owned local and sandbox computer capability."""
        self.skill_manager: SkillManager | None = None
        """Runtime-owned Skill inventory, bound after plugin initialization."""
        self.tool_image_cache = tool_image_cache
        """Runtime-owned cache for tool-returned images."""
        self.active_event_registry = active_event_registry or ActiveEventRegistry()
        """Runtime-owned active event cancellation index."""
        self.session_lock_manager = session_lock_manager or SessionLockManager()
        """Runtime-owned per-session lock manager."""
        self.session_waiter_registry = (
            session_waiter_registry or SessionWaiterRegistry()
        )
        self._persisted_group_send_objects: set[int] = set()
        """Runtime-owned interactive message waits."""
        self.demo_mode = demo_mode
        self.subagent_orchestrator = subagent_orchestrator
        self.persona_runtime_manager: PersonaRuntimeManager | None = None
        self.memory_manager: MemoryManager | None = None
        self.dashboard_extension_registry = DashboardExtensionRegistry()
        self.dashboard_extensions = DashboardExtensionAccess(
            self.dashboard_extension_registry
        )
        self._register_tasks: list[Awaitable] = []
        self._star_manager = None

    async def llm_generate(
        self,
        *,
        chat_provider_id: str,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        tools: ToolSet | None = None,
        system_prompt: str | None = None,
        contexts: list[Message] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Call the LLM to generate a response. The method will not automatically execute tool calls. If you want to use tool calls, please use `tool_loop_agent()`.

        .. versionadded:: 4.5.7 (sdk)

        Args:
            chat_provider_id: The chat provider ID to use.
            prompt: The prompt to send to the LLM, if `contexts` and `prompt` are both provided, `prompt` will be appended as the last user message
            image_urls: List of image URLs to include in the prompt, if `contexts` and `prompt` are both provided, `image_urls` will be appended to the last user message
            audio_urls: List of audio URLs or local paths to include in the prompt, if `contexts` and `prompt` are both provided, `audio_urls` will be appended to the last user message
            tools: ToolSet of tools available to the LLM
            system_prompt: System prompt to guide the LLM's behavior, if provided, it will always insert as the first system message in the context
            contexts: context messages for the LLM
            **kwargs: Additional keyword arguments for LLM generation, OpenAI compatible

        Raises:
            ChatProviderNotFoundError: If the specified chat provider ID is not found
            Exception: For other errors during LLM generation
        """
        prov = await self.provider_manager.get_provider_by_id(chat_provider_id)
        if not prov or not isinstance(prov, Provider):
            raise ProviderNotFoundError(f"Provider {chat_provider_id} not found")
        from astrbot.core.agent.request_preparation import prepare_provider_request

        request = await prepare_provider_request(
            ProviderRequest(
                prompt=prompt,
                image_urls=list(image_urls or []),
                audio_urls=list(audio_urls or []),
                func_tool=tools,
                contexts=[
                    message.model_dump() if isinstance(message, Message) else message
                    for message in contexts or []
                ],
                system_prompt=system_prompt or "",
            ),
            provider=prov,
        )
        llm_resp = await prov.text_chat(
            prompt=request.prompt,
            image_urls=request.image_urls,
            audio_urls=request.audio_urls,
            func_tool=request.func_tool,
            contexts=request.contexts,
            system_prompt=request.system_prompt,
            extra_user_content_parts=request.extra_user_content_parts,
            **kwargs,
        )
        return llm_resp

    async def tool_loop_agent(
        self,
        *,
        event: AstrMessageEvent,
        chat_provider_id: str,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        tools: ToolSet | None = None,
        system_prompt: str | None = None,
        contexts: list[Message] | None = None,
        max_steps: int = 30,
        tool_call_timeout: int = 120,
        **kwargs: Any,
    ) -> LLMResponse:
        """Run an agent loop that allows the LLM to call tools iteratively until a final answer is produced.
        If you do not pass the agent_context parameter, the method will recreate a new agent context.

        .. versionadded:: 4.5.7 (sdk)

        Args:
            chat_provider_id: The chat provider ID to use.
            prompt: The prompt to send to the LLM, if `contexts` and `prompt` are both provided, `prompt` will be appended as the last user message
            image_urls: List of image URLs to include in the prompt, if `contexts` and `prompt` are both provided, `image_urls` will be appended to the last user message
            audio_urls: List of audio URLs or local paths to include in the prompt, if `contexts` and `prompt` are both provided, `audio_urls` will be appended to the last user message
            tools: ToolSet of tools available to the LLM
            system_prompt: System prompt to guide the LLM's behavior, if provided, it will always insert as the first system message in the context
            contexts: context messages for the LLM
            max_steps: Maximum number of agent steps/LLM-tool loop rounds before stopping the loop
            **kwargs: Additional keyword arguments. The kwargs will not be passed to the LLM directly for now, but can include:
                stream: bool - whether to stream the LLM response
                agent_hooks: BaseAgentRunHooks[AstrAgentContext] - hooks to run during agent execution
                agent_context: AstrAgentContext - context to use for the agent

                other kwargs will be DIRECTLY passed to the runner.reset() method

        Returns:
            The final LLMResponse after tool calls are completed.

        Raises:
            ChatProviderNotFoundError: If the specified chat provider ID is not found
            Exception: For other errors during LLM generation
        """
        # Import here to avoid circular imports
        from astrbot.core.agent.request_preparation import prepare_provider_request
        from astrbot.core.astr_agent_context import (
            AgentContextWrapper,
            AstrAgentContext,
        )
        from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        from astrbot.core.astr_main_agent import (
            MainAgentBuildConfig,
            prepare_event_attachments,
        )

        prov = await self.provider_manager.get_provider_by_id(chat_provider_id)
        if not prov or not isinstance(prov, Provider):
            raise ProviderNotFoundError(f"Provider {chat_provider_id} not found")

        agent_hooks = kwargs.get("agent_hooks") or BaseAgentRunHooks[AstrAgentContext]()
        agent_context = kwargs.get("agent_context")

        context_ = []
        for msg in contexts or []:
            if isinstance(msg, Message):
                context_.append(msg.model_dump())
            else:
                context_.append(msg)

        request = ProviderRequest(
            prompt=prompt,
            image_urls=image_urls or [],
            audio_urls=audio_urls or [],
            func_tool=tools,
            contexts=context_,
            system_prompt=system_prompt or "",
        )
        config_data = self.get_config(umo=event.unified_msg_origin) or {}
        provider_settings = config_data.get("provider_settings") or {}
        await prepare_event_attachments(
            event,
            request,
            MainAgentBuildConfig(
                tool_call_timeout=tool_call_timeout,
                provider_settings=provider_settings,
            ),
            self,
        )
        request = await prepare_provider_request(request, provider=prov)
        if agent_context is None:
            agent_context = AstrAgentContext(
                context=self,
                event=event,
            )
        agent_runner = ToolLoopAgentRunner(self.tool_image_cache)
        tool_executor = FunctionToolExecutor()

        streaming = kwargs.get("stream", False)

        other_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in ["stream", "agent_hooks", "agent_context"]
        }
        if request.func_tool and request.func_tool.get_tool("astrbot_file_read_tool"):
            other_kwargs.setdefault(
                "tool_result_overflow_dir", get_astrbot_system_tmp_path()
            )
            other_kwargs.setdefault(
                "read_tool", request.func_tool.get_tool("astrbot_file_read_tool")
            )

        await agent_runner.reset(
            provider=prov,
            request=request,
            run_context=AgentContextWrapper(
                context=agent_context,
                tool_call_timeout=tool_call_timeout,
            ),
            tool_executor=tool_executor,
            agent_hooks=agent_hooks,
            streaming=streaming,
            **other_kwargs,
        )
        async for _ in agent_runner.step_until_done(max_steps):
            pass
        llm_resp = agent_runner.get_final_llm_resp()
        if not llm_resp:
            raise Exception("Agent did not produce a final LLM response")
        return llm_resp

    async def get_current_chat_provider_id(self, umo: str) -> str:
        """获取当前使用的聊天模型 Provider ID。

        Args:
            umo: unified_message_origin。消息会话来源 ID。

        Returns:
            指定消息会话来源当前使用的聊天模型 Provider ID。

        Raises:
            ProviderNotFoundError: 未找到。
        """
        prov = self.get_using_provider(umo)
        if not prov:
            raise ProviderNotFoundError("Provider not found")
        return prov.meta().id

    def get_registered_star(self, star_name: str) -> StarMetadata | None:
        """根据插件名获取插件的 Metadata"""
        return self.catalogs.plugins.get_by_name(star_name)

    def get_all_stars(self) -> list[StarMetadata]:
        """获取当前载入的所有插件 Metadata 的列表"""
        return list(self.catalogs.plugins)

    def get_llm_tool_manager(self) -> FunctionToolManager:
        """获取 LLM Tool Manager，其用于管理注册的所有的 Function-calling tools"""
        return self.catalogs.tools

    async def activate_llm_tool(self, name: str) -> bool:
        """激活一个已经注册的函数调用工具。

        Args:
            name: 工具名称。

        Returns:
            如果成功激活返回 True，如果没找到工具返回 False。

        Note:
            注册的工具默认是激活状态。
        """
        return await self.catalogs.tools.activate_llm_tool(name)

    async def deactivate_llm_tool(self, name: str) -> bool:
        """停用一个已经注册的函数调用工具。

        Args:
            name: 工具名称。

        Returns:
            如果成功停用返回 True，如果没找到工具返回 False。
        """
        return await self.catalogs.tools.deactivate_llm_tool(name)

    def get_provider_by_id(
        self,
        provider_id: str,
    ) -> (
        Provider | TTSProvider | STTProvider | EmbeddingProvider | RerankProvider | None
    ):
        """通过 ID 获取对应的 LLM Provider。

        Args:
            provider_id: 提供者 ID。

        Returns:
            提供者实例，如果未找到则返回 None。

        Note:
            如果提供者 ID 存在但未找到提供者，会记录警告日志。
        """
        prov = self.provider_manager.inst_map.get(provider_id)
        if provider_id and not prov:
            logger.warning(
                f"没有找到 ID 为 {provider_id} 的提供商，这可能是由于您修改了提供商（模型）ID 导致的。"
            )
        return prov

    def get_all_providers(self) -> list[Provider]:
        """获取所有用于文本生成任务的 LLM Provider(Chat_Completion 类型)。"""
        return self.provider_manager.provider_insts

    def get_all_tts_providers(self) -> list[TTSProvider]:
        """获取所有用于 TTS 任务的 Provider。"""
        return self.provider_manager.tts_provider_insts

    def get_all_stt_providers(self) -> list[STTProvider]:
        """获取所有用于 STT 任务的 Provider。"""
        return self.provider_manager.stt_provider_insts

    def get_all_embedding_providers(self) -> list[EmbeddingProvider]:
        """获取所有用于 Embedding 任务的 Provider。"""
        return self.provider_manager.embedding_provider_insts

    def get_using_provider(self, umo: str | None = None) -> Provider | None:
        """获取当前使用的用于文本生成任务的 LLM Provider(Chat_Completion 类型)。

        Args:
            umo: unified_message_origin 值，如果传入并且用户启用了提供商会话隔离，
                 则使用该会话偏好的对话模型（提供商）。

        Returns:
            当前使用的对话模型（提供商），如果未设置则返回 None。

        Raises:
            ValueError: 该会话来源配置的的对话模型（提供商）的类型不正确。
        """
        prov = self.provider_manager.get_using_provider(
            provider_type=ProviderType.CHAT_COMPLETION,
            umo=umo,
        )
        if prov is None:
            return None
        if not isinstance(prov, Provider):
            raise ValueError(
                f"该会话来源的对话模型（提供商）的类型不正确: {type(prov)}"
            )
        return prov

    def get_using_tts_provider(self, umo: str | None = None) -> TTSProvider | None:
        """获取当前使用的用于 TTS 任务的 Provider。

        Args:
            umo: unified_message_origin 值，如果传入，则使用该会话偏好的提供商。

        Returns:
            当前使用的 TTS 提供者，如果未设置则返回 None。

        Raises:
            ValueError: 返回的提供者不是 TTSProvider 类型。
        """
        prov = self.provider_manager.get_using_provider(
            provider_type=ProviderType.TEXT_TO_SPEECH,
            umo=umo,
        )
        if prov and not isinstance(prov, TTSProvider):
            raise ValueError("返回的 Provider 不是 TTSProvider 类型")
        return prov

    def get_using_stt_provider(self, umo: str | None = None) -> STTProvider | None:
        """获取当前使用的用于 STT 任务的 Provider。

        Args:
            umo: unified_message_origin 值，如果传入，则使用该会话偏好的提供商。

        Returns:
            当前使用的 STT 提供者，如果未设置则返回 None。

        Raises:
            ValueError: 返回的提供者不是 STTProvider 类型。
        """
        prov = self.provider_manager.get_using_provider(
            provider_type=ProviderType.SPEECH_TO_TEXT,
            umo=umo,
        )
        if prov and not isinstance(prov, STTProvider):
            raise ValueError("返回的 Provider 不是 STTProvider 类型")
        return prov

    def get_config(self, umo: str | None = None) -> AstrBotConfig:
        """获取 AstrBot 的配置。

        Args:
            umo: unified_message_origin 值，用于获取特定会话的配置。

        Returns:
            AstrBot 配置对象。

        Note:
            如果不提供 umo 参数，将返回默认配置。
        """
        if not umo:
            # 使用默认配置
            return self._config
        return self.astrbot_config_mgr.get_conf(umo)

    async def send_message(
        self,
        session: str | MessageSession,
        message_chain: MessageChain,
    ) -> PlatformSendResult:
        """根据 session(unified_msg_origin) 主动发送消息。

        Args:
            session: 消息会话。通过 event.session 或者 event.unified_msg_origin 获取。
            message_chain: 消息链。

        Returns:
            标准化发送结果。

        Raises:
            ValueError: session 字符串不合法时抛出。

        Note:
            当 session 为字符串时，会尝试解析为 MessageSession 对象。
            qq_official(QQ 官方 API 平台) 不支持此方法。
        """
        if isinstance(session, str):
            try:
                session = MessageSession.from_str(session)
            except Exception as e:
                raise ValueError("不合法的 session 字符串: " + str(e))

        result = await self._platform_manager.send_to_session(session, message_chain)
        if result.success:
            await self._persist_accepted_group_send(session, message_chain)
            return result
        logger.warning(
            "send_message failed for session %s: %s",
            str(session),
            result.error_message or "unknown error",
        )
        return result

    async def _persist_accepted_group_send(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ) -> None:
        """Persist one accepted assistant group send without duplicating retries."""
        if session.message_type.value != "GroupMessage":
            return
        if session.platform_id == "webchat":
            return
        marker = id(message_chain)
        if marker in self._persisted_group_send_objects:
            return
        record_id = await self._persist_group_message_chain(
            platform_id=session.platform_id,
            group_id=str(session),
            message_chain=message_chain,
            role="assistant",
            sender_id="assistant",
            sender_name="AstrBot",
            error_context="accepted group message",
        )
        if record_id is not None:
            self._persisted_group_send_objects.add(marker)
            if len(self._persisted_group_send_objects) > 2048:
                self._persisted_group_send_objects.clear()

    async def persist_inbound_group_message(self, event: AstrMessageEvent) -> None:
        """Persist one inbound group message before plugin processing.

        Args:
            event: The normalized inbound platform event.
        """
        if (
            event.get_message_type() != MessageType.GROUP_MESSAGE
            or event.get_platform_name() == "webchat"
        ):
            return
        record_id = await self._persist_group_message_chain(
            platform_id=event.get_platform_id(),
            group_id=event.unified_msg_origin,
            message_chain=MessageChain(chain=list(event.get_messages())),
            role="user",
            sender_id=event.get_sender_id(),
            sender_name=event.get_sender_name(),
            error_context="inbound group message",
        )
        if record_id is not None:
            event.set_extra("_group_history_current_id", record_id)

    async def persist_accepted_group_response(
        self,
        event: AstrMessageEvent,
        receipt: DeliveryReceipt,
    ) -> None:
        """Persist the accepted portion of one group response.

        Args:
            event: The event that produced the response.
            receipt: The platform acceptance receipt for that response.
        """
        if (
            event.get_message_type() != MessageType.GROUP_MESSAGE
            or event.get_platform_name() == "webchat"
            or not receipt.accepted_attempts
            or event.get_extra("_group_history_assistant_persisted", False)
        ):
            return
        result = event.get_result()
        if result is None or not result.chain:
            return
        message_chain = MessageChain(chain=list(result.chain))
        if receipt.status != "accepted":
            if not receipt.history_text:
                return
            message_chain = MessageChain(chain=[Plain(receipt.history_text)])
        record_id = await self._persist_group_message_chain(
            platform_id=event.get_platform_id(),
            group_id=event.unified_msg_origin,
            message_chain=message_chain,
            role="assistant",
            sender_id=event.get_self_id() or "assistant",
            sender_name="AstrBot",
            error_context="accepted group response",
        )
        if record_id is not None:
            event.set_extra("_group_history_assistant_persisted", True)

    async def _persist_group_message_chain(
        self,
        *,
        platform_id: str,
        group_id: str,
        message_chain: MessageChain,
        role: str,
        sender_id: str | None,
        sender_name: str | None,
        error_context: str,
    ) -> int | None:
        """Persist one enabled group history record and return its identifier."""
        try:
            settings = self.get_config(umo=group_id).get("provider_ltm_settings", {})
            if not settings.get("group_message_history_enable", False):
                return None
            try:
                max_messages = max(
                    1, int(settings.get("group_message_history_max_cnt", 700))
                )
            except TypeError, ValueError:
                max_messages = 700
            record = await self.message_history_manager.insert_message_chain(
                platform_id=platform_id,
                user_id=group_id,
                message_chain=message_chain,
                role=role,
                is_group=True,
                sender_id=sender_id,
                sender_name=sender_name,
                max_messages=max_messages,
            )
            return record.id if record is not None else None
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to persist %s.", error_context)
            return None

    def add_llm_tools(self, *tools: FunctionTool) -> None:
        """添加 LLM 工具。

        Args:
            *tools: 要添加的函数工具对象。

        Note:
            如果工具已存在，会替换已存在的工具。
        """
        tool_name = {tool.name for tool in self.catalogs.tools.func_list}
        module_path = ""
        for tool in tools:
            if not module_path:
                tool.handler_module_path = _resolve_tool_handler_module_path(
                    self.catalogs,
                    tool,
                )
                module_path = tool.handler_module_path
            else:
                tool.handler_module_path = module_path
            logger.info(
                f"plugin(module_path {module_path}) added LLM tool: {tool.name}"
            )

            if tool.name in tool_name:
                logger.warning("替换已存在的 LLM 工具: " + tool.name)
                self.catalogs.tools.remove_tool(tool.name)
            self.catalogs.tools.func_list.append(tool)

    """
    以下的方法已经不推荐使用。请从 AstrBot 文档查看更好的注册方式。
    """

    def get_event_queue(self) -> Queue:
        """获取事件队列。"""
        return self._event_queue

    def commit_event(self, event: AstrMessageEvent) -> bool:
        """提交一个事件到事件队列。"""
        try:
            self._event_queue.put_nowait(event)
        except QueueFull:
            logger.warning(
                "Event queue full; dropping event from %s",
                event.unified_msg_origin,
            )
            return False
        return True

    async def refresh_platform_commands(self) -> None:
        """Refresh platform command surfaces after plugin catalog changes."""
        await self._platform_manager.refresh_registered_commands()

    async def invoke_platform_action(
        self,
        platform_id: str,
        action_name: str,
        **kwargs: Any,
    ) -> dict[str, object]:
        """Invoke a declared proactive platform action through PlatformManager."""
        return await self._platform_manager.invoke_action(
            platform_id,
            action_name,
            **kwargs,
        )

    async def invoke_platform_capability(
        self,
        platform_id: str,
        capability_name: str,
        action_name: str,
        **kwargs: Any,
    ) -> object:
        """Invoke a versioned platform capability through its owner."""
        return await self._platform_manager.invoke_capability(
            platform_id,
            capability_name,
            action_name,
            **kwargs,
        )

    def get_platform_capabilities(self, platform_id: str) -> tuple[object, ...]:
        """Return the immutable capability snapshot for a platform instance."""
        return self._platform_manager.get_platform_capabilities(platform_id)

    async def invoke_event_platform_action(
        self,
        event: AstrMessageEvent,
        action_name: str,
        **kwargs: Any,
    ) -> dict[str, object]:
        """Invoke a platform action for the platform that produced the event."""
        return await self.invoke_platform_action(
            event.get_platform_id(),
            action_name,
            **kwargs,
        )

    def create_platform_event(
        self,
        platform: str,
        event_message: Any,
        *,
        is_wake: bool = True,
    ) -> None:
        """Create and commit an event through a platform adapter lookup."""
        self._platform_manager.create_event(
            platform,
            event_message,
            is_wake=is_wake,
        )

    def register_provider(self, provider: Provider) -> None:
        """注册一个 LLM Provider(Chat_Completion 类型)。

        Args:
            provider: 提供者实例。
        """
        self.provider_manager.provider_insts.append(provider)

    def register_commands(
        self,
        star_name: str,
        command_name: str,
        desc: str,
        priority: int,
        awaitable: Callable[..., Awaitable[Any]],
        use_regex=False,
        ignore_prefix=False,
    ) -> None:
        """[DEPRECATED]注册一个命令。

        Args:
            star_name: 插件（Star）名称。
            command_name: 命令名称。
            desc: 命令描述。
            priority: 优先级。1-10。
            awaitable: 异步处理函数。
            use_regex: 是否使用正则表达式匹配命令。
            ignore_prefix: 是否忽略命令前缀。

        Note:
            推荐使用装饰器注册指令。该方法将在未来的版本中被移除。
        """
        md = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name=awaitable.__module__ + "_" + awaitable.__name__,
            handler_name=awaitable.__name__,
            handler_module_path=awaitable.__module__,
            handler=awaitable,
            event_filters=[],
            desc=desc,
        )
        if use_regex:
            md.event_filters.append(RegexFilter(regex=command_name))
        else:
            md.event_filters.append(
                CommandFilter(command_name=command_name, handler_md=md),
            )
        self.catalogs.handlers.append(md)

    def register_task(self, task: Awaitable, desc: str) -> None:
        """[DEPRECATED]注册一个异步任务。

        Args:
            task: 异步任务。
            desc: 任务描述。

        Note:
            该方法已弃用。
        """
        self._register_tasks.append(task)
