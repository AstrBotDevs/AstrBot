from asyncio import Queue
from typing import List, Union

from astrbot.core.provider.provider import (
    Provider,
    TTSProvider,
    STTProvider,
    EmbeddingProvider,
)
from astrbot.core.provider.entities import ProviderType
from astrbot.core.db import BaseDatabase
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.platform import Platform
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.persona_mgr import PersonaManager
from .star import star_registry, StarMetadata, star_map
from .star_handler import star_handlers_registry, StarHandlerMetadata, EventType
from .filter.command import CommandFilter
from .filter.regex import RegexFilter
from typing import Awaitable
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.star.filter.platform_adapter_type import (
    PlatformAdapterType,
    ADAPTER_NAME_2_TYPE,
)
from deprecated import deprecated


class Context:
    """
    暴露给插件的接口上下文。
    """

    registered_web_apis: list = []

    # back compatibility
    _register_tasks: List[Awaitable] = []
    _star_manager = None

    def __init__(
        self,
        event_queue: Queue,
        config: AstrBotConfig,
        db: BaseDatabase,
        provider_manager: ProviderManager,
        platform_manager: PlatformManager,
        conversation_manager: ConversationManager,
        message_history_manager: PlatformMessageHistoryManager,
        persona_manager: PersonaManager,
        astrbot_config_mgr: AstrBotConfigManager,
    ):
        self._event_queue = event_queue
        """事件队列。消息平台通过事件队列传递消息事件。"""
        self._config = config
        """AstrBot 默认配置"""
        self._db = db
        """AstrBot 数据库"""
        self.provider_manager = provider_manager
        self.platform_manager = platform_manager
        self.conversation_manager = conversation_manager
        self.message_history_manager = message_history_manager
        self.persona_manager = persona_manager
        self.astrbot_config_mgr = astrbot_config_mgr

    def get_registered_star(self, star_name: str) -> StarMetadata | None:
        """根据插件名获取插件的 Metadata"""
        for star in star_registry:
            if star.name == star_name:
                return star

    def get_all_stars(self) -> List[StarMetadata]:
        """获取当前载入的所有插件 Metadata 的列表"""
        return star_registry

    def get_llm_tool_manager(self) -> FunctionToolManager:
        """获取 LLM Tool Manager，其用于管理注册的所有的 Function-calling tools"""
        return self.provider_manager.llm_tools

    def activate_llm_tool(self, name: str) -> bool:
        """激活一个已经注册的函数调用工具。注册的工具默认是激活状态。

        Returns:
            如果没找到，会返回 False
        """
        return self.provider_manager.llm_tools.activate_llm_tool(name, star_map)

    def deactivate_llm_tool(self, name: str) -> bool:
        """停用一个已经注册的函数调用工具。

        Returns:
            如果没找到，会返回 False"""
        return self.provider_manager.llm_tools.deactivate_llm_tool(name)

    def register_provider(self, provider: Provider):
        """
        注册一个 LLM Provider(Chat_Completion 类型)。
        """
        self.provider_manager.provider_insts.append(provider)

    def get_provider_by_id(self, provider_id: str) -> Provider | None:
        """通过 ID 获取对应的 LLM Provider(Chat_Completion 类型)。"""
        return self.provider_manager.inst_map.get(provider_id)

    def get_all_providers(self) -> List[Provider]:
        """获取所有用于文本生成任务的 LLM Provider(Chat_Completion 类型)。"""
        return self.provider_manager.provider_insts

    def get_all_tts_providers(self) -> List[TTSProvider]:
        """获取所有用于 TTS 任务的 Provider。"""
        return self.provider_manager.tts_provider_insts

    def get_all_stt_providers(self) -> List[STTProvider]:
        """获取所有用于 STT 任务的 Provider。"""
        return self.provider_manager.stt_provider_insts

    def get_all_embedding_providers(self) -> List[EmbeddingProvider]:
        """获取所有用于 Embedding 任务的 Provider。"""
        return self.provider_manager.embedding_provider_insts

    def get_using_provider(self, umo: str | None = None) -> Provider | None:
        """
        获取当前使用的用于文本生成任务的 LLM Provider(Chat_Completion 类型)。通过 /provider 指令切换。

        Args:
            umo(str): unified_message_origin 值，如果传入并且用户启用了提供商会话隔离，则使用该会话偏好的提供商。
        """
        return self.provider_manager.get_using_provider(
            provider_type=ProviderType.CHAT_COMPLETION,
            umo=umo,
        )

    def get_using_tts_provider(self, umo: str | None = None) -> TTSProvider:
        """
        获取当前使用的用于 TTS 任务的 Provider。

        Args:
            umo(str): unified_message_origin 值，如果传入，则使用该会话偏好的提供商。
        """
        return self.provider_manager.get_using_provider(
            provider_type=ProviderType.TEXT_TO_SPEECH,
            umo=umo,
        )

    def get_using_stt_provider(self, umo: str | None = None) -> STTProvider:
        """
        获取当前使用的用于 STT 任务的 Provider。

        Args:
            umo(str): unified_message_origin 值，如果传入，则使用该会话偏好的提供商。
        """
        return self.provider_manager.get_using_provider(
            provider_type=ProviderType.SPEECH_TO_TEXT,
            umo=umo,
        )

    def get_config(self, umo: str | None = None) -> AstrBotConfig:
        """获取 AstrBot 的配置。"""
        if not umo:
            # using default config
            return self._config
        else:
            return self.astrbot_config_mgr.get_conf(umo)

    def get_db(self) -> BaseDatabase:
        """获取 AstrBot 数据库。"""
        return self._db

    def get_event_queue(self) -> Queue:
        """
        获取事件队列。
        """
        return self._event_queue

    @deprecated(version="4.0.0", reason="Use get_platform_inst instead")
    def get_platform(
        self, platform_type: Union[PlatformAdapterType, str]
    ) -> Platform | None:
        """
        获取指定类型的平台适配器。

        该方法已经过时，请使用 get_platform_inst 方法。(>= AstrBot v4.0.0)
        """
        for platform in self.platform_manager.platform_insts:
            name = platform.meta().name
            if isinstance(platform_type, str):
                if name == platform_type:
                    return platform
            else:
                if (
                    name in ADAPTER_NAME_2_TYPE
                    and ADAPTER_NAME_2_TYPE[name] & platform_type
                ):
                    return platform

    def get_platform_inst(self, platform_id: str) -> Platform | None:
        """
        获取指定 ID 的平台适配器实例。

        Args:
            platform_id (str): 平台适配器的唯一标识符。你可以通过 event.get_platform_id() 获取。

        Returns:
            Platform: 平台适配器实例，如果未找到则返回 None。
        """
        for platform in self.platform_manager.platform_insts:
            if platform.meta().id == platform_id:
                return platform

    async def send_message(
        self, session: Union[str, MessageSesion], message_chain: MessageChain
    ) -> bool:
        """
        根据 session(unified_msg_origin) 主动发送消息。

        @param session: 消息会话。通过 event.session 或者 event.unified_msg_origin 获取。
        @param message_chain: 消息链。

        @return: 是否找到匹配的平台。

        当 session 为字符串时，会尝试解析为 MessageSesion 对象，如果解析失败，会抛出 ValueError 异常。

        NOTE: qq_official(QQ 官方 API 平台) 不支持此方法
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
        return False

    """
    以下的方法已经不推荐使用。请从 AstrBot 文档查看更好的注册方式。
    """

    def register_llm_tool(
        self, name: str, func_args: list, desc: str, func_obj: Awaitable
    ) -> None:
        """
        为函数调用（function-calling / tools-use）添加工具。

        @param name: 函数名
        @param func_args: 函数参数列表，格式为 [{"type": "string", "name": "arg_name", "description": "arg_description"}, ...]
        @param desc: 函数描述
        @param func_obj: 异步处理函数。

        异步处理函数会接收到额外的的关键词参数：event: AstrMessageEvent, context: Context。
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
        self.provider_manager.llm_tools.add_func(
            name, func_args, desc, func_obj, func_obj
        )

    def unregister_llm_tool(self, name: str) -> None:
        """删除一个函数调用工具。如果再要启用，需要重新注册。"""
        self.provider_manager.llm_tools.remove_func(name)

    def register_commands(
        self,
        star_name: str,
        command_name: str,
        desc: str,
        priority: int,
        awaitable: Awaitable,
        use_regex=False,
        ignore_prefix=False,
    ):
        """
        注册一个命令。

        [Deprecated] 推荐使用装饰器注册指令。该方法将在未来的版本中被移除。

        @param star_name: 插件（Star）名称。
        @param command_name: 命令名称。
        @param desc: 命令描述。
        @param priority: 优先级。1-10。
        @param awaitable: 异步处理函数。

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
                CommandFilter(command_name=command_name, handler_md=md)
            )
        star_handlers_registry.append(md)

    def register_task(self, task: Awaitable, desc: str):
        """
        注册一个异步任务。
        """
        self._register_tasks.append(task)

    def register_web_api(
        self, route: str, view_handler: Awaitable, methods: list, desc: str
    ):
        for idx, api in enumerate(self.registered_web_apis):
            if api[0] == route and methods == api[2]:
                self.registered_web_apis[idx] = (route, view_handler, methods, desc)
                return
        self.registered_web_apis.append((route, view_handler, methods, desc))
