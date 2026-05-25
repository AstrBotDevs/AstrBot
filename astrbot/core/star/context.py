from __future__ import annotations

import logging
from asyncio import Queue
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol

from deprecated import deprecated

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.message import Message
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db import BaseDatabase
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.platform import Platform
from astrbot.core.platform.astr_message_event import AstrMessageEvent, MessageSesion
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, ProviderType
from astrbot.core.provider.func_tool_manager import FunctionTool, FunctionToolManager
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.provider import (
    EmbeddingProvider,
    Provider,
    RerankProvider,
    STTProvider,
    TTSProvider,
)
from astrbot.core.star.filter.platform_adapter_type import (
    ADAPTER_NAME_2_TYPE,
    PlatformAdapterType,
)
from astrbot.core.subagent_orchestrator import SubAgentOrchestrator

from ..exceptions import ProviderNotFoundError
from .filter.command import CommandFilter
from .filter.regex import RegexFilter
from .star import StarMetadata, star_map, star_registry
from .star_handler import EventType, StarHandlerMetadata, star_handlers_registry

logger = logging.getLogger("astrbot")

if TYPE_CHECKING:
    from astrbot.core.cron.manager import CronJobManager
else:
    CronJobManager = Any


class PlatformManagerProtocol(Protocol):
    platform_insts: list[Platform]


class Context:
    """暴露给插件的接口上下文。"""

    registered_web_apis: list = []

    # 向后兼容的变量
    _register_tasks: list[Awaitable] = []
    _star_manager = None

    def __init__(
        self,
        event_queue: Queue,
        config: AstrBotConfig,
        db: BaseDatabase,
        provider_manager: ProviderManager,
        platform_manager: PlatformManagerProtocol,
        conversation_manager: ConversationManager,
        message_history_manager: PlatformMessageHistoryManager,
        persona_manager: PersonaManager,
        astrbot_config_mgr: AstrBotConfigManager,
        knowledge_base_manager: KnowledgeBaseManager,
        cron_manager: CronJobManager,
        subagent_orchestrator: SubAgentOrchestrator | None = None,
    ) -> None:
        self._event_queue = event_queue
        """事件队列。消息平台通过事件队列传递消息事件。"""
        self._config = config
        """AstrBot 默认配置"""
        self._db = db
        """AstrBot 数据库"""
        self.provider_manager = provider_manager
        """模型提供商管理器"""
        self.platform_manager = platform_manager
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
        self.subagent_orchestrator = subagent_orchestrator

    async def llm_generate(
        self,
        *,
        chat_provider_id: str,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
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
        llm_resp = await prov.text_chat(
            prompt=prompt,
            image_urls=image_urls,
            func_tool=tools,
            contexts=contexts,
            system_prompt=system_prompt,
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
        tools: ToolSet | None = None,
        system_prompt: str | None = None,
        contexts: list[Message] | None = None,
        max_steps: int = 30,
        tool_call_timeout: int = 60,
        **kwargs: Any,
    ) -> LLMResponse:
        """Run an agent loop that allows the LLM to call tools iteratively until a final answer is produced.
        If you do not pass the agent_context parameter, the method will recreate a new agent context.

        .. versionadded:: 4.5.7 (sdk)

        Args:
            chat_provider_id: The chat provider ID to use.
            prompt: The prompt to send to the LLM, if `contexts` and `prompt` are both provided, `prompt` will be appended as the last user message
            image_urls: List of image URLs to include in the prompt, if `contexts` and `prompt` are both provided, `image_urls` will be appended to the last user message
            tools: ToolSet of tools available to the LLM
            system_prompt: System prompt to guide the LLM's behavior, if provided, it will always insert as the first system message in the context
            contexts: context messages for the LLM
            max_steps: Maximum number of tool calls before stopping the loop
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
        from astrbot.core.astr_agent_context import (
            AgentContextWrapper,
            AstrAgentContext,
        )
        from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor

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
            func_tool=tools,
            contexts=context_,
            system_prompt=system_prompt or "",
        )
        if agent_context is None:
            agent_context = AstrAgentContext(
                context=self,
                event=event,
            )
        agent_runner = ToolLoopAgentRunner()
        tool_executor = FunctionToolExecutor()

        streaming = kwargs.get("stream", False)

        other_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in ["stream", "agent_hooks", "agent_context"]
        }

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
        for star in star_registry:
            if star.name == star_name:
                return star

    def get_all_stars(self) -> list[StarMetadata]:
        """获取当前载入的所有插件 Metadata 的列表"""
        return star_registry

    def get_llm_tool_manager(self) -> FunctionToolManager:
        """获取 LLM Tool Manager，其用于管理注册的所有的 Function-calling tools"""
        return self.provider_manager.llm_tools

    def activate_llm_tool(self, name: str) -> bool:
        """激活一个已经注册的函数调用工具。

        Args:
            name: 工具名称。

        Returns:
            如果成功激活返回 True，如果没找到工具返回 False。

        Note:
            注册的工具默认是激活状态。
        """
        return self.provider_manager.llm_tools.activate_llm_tool(name, star_map)

    def deactivate_llm_tool(self, name: str) -> bool:
        """停用一个已经注册的函数调用工具。

        Args:
            name: 工具名称。

        Returns:
            如果成功停用返回 True，如果没找到工具返回 False。
        """
        return self.provider_manager.llm_tools.deactivate_llm_tool(name)

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
        session: str | MessageSesion,
        message_chain: MessageChain,
    ) -> bool:
        """根据 session(unified_msg_origin) 主动发送消息。

        Args:
            session: 消息会话。通过 event.session 或者 event.unified_msg_origin 获取。
            message_chain: 消息链。

        Returns:
            是否找到匹配的平台。

        Raises:
            ValueError: session 字符串不合法时抛出。

        Note:
            当 session 为字符串时，会尝试解析为 MessageSession 对象。(类名为MessageSesion是因为历史遗留拼写错误)
            qq_official(QQ 官方 API 平台) 不支持此方法。
        """
        if isinstance(session, str):
            try:
                session = MessageSesion.from_str(session)
            except BaseException as e:
                raise ValueError("不合法的 session 字符串: " + str(e))

        for platform in self.platform_manager.platform_insts:
            if platform.meta().id == session.platform_name:
                await platform.send_by_session(session, message_chain)
                return True
        logger.warning(
            f"cannot find platform for session {str(session)}, message not sent"
        )
        return False

    def add_llm_tools(self, *tools: FunctionTool) -> None:
        """添加 LLM 工具。

        Args:
            *tools: 要添加的函数工具对象。

        Note:
            如果工具已存在，会替换已存在的工具。
        """
        tool_name = {tool.name for tool in self.provider_manager.llm_tools.func_list}
        module_path = ""
        for tool in tools:
            if not module_path:
                _parts = []
                module_part = tool.__module__.split(".")
                flags = ["builtin_stars", "plugins"]
                for i, part in enumerate(module_part):
                    _parts.append(part)
                    if part in flags and i + 1 < len(module_part):
                        _parts.append(module_part[i + 1])
                        module_part.append("main")
                        break
                tool.handler_module_path = ".".join(_parts)
                module_path = tool.handler_module_path
            else:
                tool.handler_module_path = module_path
            logger.info(
                f"plugin(module_path {module_path}) added LLM tool: {tool.name}"
            )

            if tool.name in tool_name:
                logger.warning("替换已存在的 LLM 工具: " + tool.name)
                self.provider_manager.llm_tools.remove_func(tool.name)
            self.provider_manager.llm_tools.func_list.append(tool)

    def register_web_api(
        self,
        route: str,
        view_handler: Awaitable,
        methods: list,
        desc: str,
    ) -> None:
        """注册 Web API。

        Args:
            route: API 路由路径。
            view_handler: 异步视图处理函数。
            methods: HTTP 方法列表。
            desc: API 描述。

        Note:
            如果相同路由和方法已注册，会替换现有的 API。
        """
        for idx, api in enumerate(self.registered_web_apis):
            if api[0] == route and methods == api[2]:
                self.registered_web_apis[idx] = (route, view_handler, methods, desc)
                return
        self.registered_web_apis.append((route, view_handler, methods, desc))

    """
    以下的方法已经不推荐使用。请从 AstrBot 文档查看更好的注册方式。
    """

    def get_event_queue(self) -> Queue:
        """获取事件队列。"""
        return self._event_queue

    @deprecated(version="4.0.0", reason="Use get_platform_inst instead")
    def get_platform(self, platform_type: PlatformAdapterType | str) -> Platform | None:
        """获取指定类型的平台适配器。

        Args:
            platform_type: 平台类型或平台名称。

        Returns:
            平台适配器实例，如果未找到则返回 None。

        Note:
            该方法已经过时，请使用 get_platform_inst 方法。(>= AstrBot v4.0.0)
        """
        for platform in self.platform_manager.platform_insts:
            name = platform.meta().name
            if isinstance(platform_type, str):
                if name == platform_type:
                    return platform
            elif (
                name in ADAPTER_NAME_2_TYPE
                and ADAPTER_NAME_2_TYPE[name] & platform_type
            ):
                return platform

    def get_platform_inst(self, platform_id: str) -> Platform | None:
        """获取指定 ID 的平台适配器实例。

        Args:
            platform_id: 平台适配器的唯一标识符。

        Returns:
            平台适配器实例，如果未找到则返回 None。

        Note:
            可以通过 event.get_platform_id() 获取平台 ID。
        """
        for platform in self.platform_manager.platform_insts:
            if platform.meta().id == platform_id:
                return platform

    def get_db(self) -> BaseDatabase:
        """获取 AstrBot 数据库。

        Returns:
            数据库实例。
        """
        return self._db

    def register_provider(self, provider: Provider) -> None:
        """注册一个 LLM Provider(Chat_Completion 类型)。

        Args:
            provider: 提供者实例。
        """
        self.provider_manager.provider_insts.append(provider)

    def register_llm_tool(
        self,
        name: str,
        func_args: list,
        desc: str,
        func_obj: Callable[..., Awaitable[Any]],
    ) -> None:
        """[DEPRECATED]为函数调用（function-calling / tools-use）添加工具。

        Args:
            name: 函数名。
            func_args: 函数参数列表，格式为
                [{"type": "string", "name": "arg_name", "description": "arg_description"}, ...]。
            desc: 函数描述。
            func_obj: 异步处理函数。

        Note:
            异步处理函数会接收到额外的关键词参数：event: AstrMessageEvent, context: Context。
            该方法已弃用，请使用新的注册方式。
        """
        md = StarHandlerMetadata(
            event_type=EventType.OnLLMRequestEvent,
            handler_full_name=func_obj.__module__ + "_" + func_obj.__name__,
            handler_name=func_obj.__name__,
            handler_module_path=func_obj.__module__,
            handler=func_obj,
            event_filters=[],
            desc=desc,
        )
        star_handlers_registry.append(md)
        self.provider_manager.llm_tools.add_func(name, func_args, desc, func_obj)

    def unregister_llm_tool(self, name: str) -> None:
        """[DEPRECATED]删除一个函数调用工具。

        Args:
            name: 工具名称。

        Note:
            如果再要启用，需要重新注册。
            该方法已弃用。
        """
        self.provider_manager.llm_tools.remove_func(name)

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
        star_handlers_registry.append(md)

    def register_task(self, task: Awaitable, desc: str) -> None:
        """[DEPRECATED]注册一个异步任务。

        Args:
            task: 异步任务。
            desc: 任务描述。

        Note:
            该方法已弃用。
        """
        self._register_tasks.append(task)
