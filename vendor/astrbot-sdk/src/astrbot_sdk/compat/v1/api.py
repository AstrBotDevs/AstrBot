"""Install the astrbot.api compat namespace into sys.modules.

Old plugins import from astrbot.api.*; in the isolated legacy Runner those
imports must resolve to the compat implementation, and imports of the real
astrbot.core.* must fail loudly (isolation would be fake otherwise).
"""

from __future__ import annotations

import logging
import sys
from types import ModuleType
from typing import Any

_installed = False


class _ContextWrapper:
    """Legacy ContextWrapper shell; generic subscription is a no-op."""

    def __init__(self, context: Any = None, **kwargs: Any) -> None:
        self.context = context
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __class_getitem__(cls, item: Any) -> type:
        return cls


class _AstrAgentContext:
    """Legacy AstrAgentContext shell (event/context carrier)."""

    def __init__(self, context: Any = None, event: Any = None, **_: Any) -> None:
        self.context = context
        self.event = event


class _AgentMessage:
    """Legacy agent message shell (OpenAI-format dict behaviour)."""

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def model_dump(self, **_: Any) -> dict:
        return dict(self.__dict__)


class _AgentPart(_AgentMessage):
    """Legacy agent content-part shell."""


class _ShellRecord:
    """Generic shell for type-only records referenced by legacy plugins."""

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __class_getitem__(cls, item: Any) -> type:
        return cls


def _namespace_package(name: str) -> ModuleType:
    """Build one empty package placeholder for whitelisted submodules."""
    module = ModuleType(name)
    module.__path__ = []
    return module


class _BlockedModule(ModuleType):
    """Module placeholder that fails loudly when touched."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.__path__ = []  # mark as package so submodule imports reach us

    def __getattr__(self, name: str) -> Any:
        raise ImportError(
            f"{self.__name__} is unavailable in isolated legacy mode; "
            "plugins importing it must run in-process"
        )


class _SharedPreferences:
    """Legacy sp facade backed by plugin-scoped KV storage."""

    _ctx: Any = None

    @classmethod
    def initialize(cls, ctx: Any) -> None:
        """Bind the plugin context (called once by the compat loader)."""
        cls._ctx = ctx

    def _storage(self) -> Any:
        if _SharedPreferences._ctx is None:
            raise ValueError("sp not initialized")
        return _SharedPreferences._ctx.storage

    async def get(self, scope: str, key: str, default: Any = None) -> Any:
        return await self._storage().get(f"sp:{scope}:{key}", default)

    async def put(self, scope: str, key: str, value: Any) -> None:
        await self._storage().set(f"sp:{scope}:{key}", value)

    async def remove(self, scope: str, key: str) -> None:
        await self._storage().delete(f"sp:{scope}:{key}")

    async def session_get(
        self,
        umo: str,
        key: str,
        default: Any = None,
        **_: Any,
    ) -> Any:
        return await self._storage().get(f"sp:session:{umo}:{key}", default)

    async def session_put(self, umo: str, key: str, value: Any) -> None:
        await self._storage().set(f"sp:session:{umo}:{key}", value)


def _utils_io_mod() -> ModuleType:
    """Build the astrbot.core.utils.io shim (pure local helpers only)."""
    from . import utils

    mod = ModuleType("astrbot.core.utils.io")
    for name in (
        "download_image_by_url",
        "download_file",
        "save_temp_img",
        "ensure_dir",
        "remove_dir",
        "port_checker",
        "file_to_base64",
        "get_local_ip_addresses",
    ):
        setattr(mod, name, getattr(utils, name))
    return mod


def _utils_session_lock_mod() -> ModuleType:
    """Build the astrbot.core.utils.session_lock shim."""
    from . import utils

    mod = ModuleType("astrbot.core.utils.session_lock")
    mod.SessionLockManager = utils.SessionLockManager
    mod.session_lock_manager = utils.session_lock_manager
    return mod


def _utils_media_utils_mod() -> ModuleType:
    """Build the astrbot.core.utils.media_utils shim (pure path helpers)."""
    from . import utils

    mod = ModuleType("astrbot.core.utils.media_utils")
    mod.is_file_uri = utils.is_file_uri
    mod.file_uri_to_path = utils.file_uri_to_path
    mod.describe_media_ref = utils.describe_media_ref
    return mod


def _unsupported(feature: str) -> Any:
    def raise_loud(*args: Any, **kwargs: Any) -> Any:
        from .errors import IsolationUnsupportedError

        raise IsolationUnsupportedError(
            f"{feature} is unavailable in isolated legacy mode; "
            "plugins needing it must run in-process"
        )

    return raise_loud


def _unsupported_agent(*args: Any, **kwargs: Any) -> Any:
    return _unsupported("custom agent registration (@agent)")(*args, **kwargs)


def install(host_version: str | None = None) -> None:
    """Install the compat astrbot.api namespace and the core blocker.

    Args:
        host_version: AstrBot core version reported by the Host, exposed to
            legacy plugins as astrbot.core.config.default.VERSION.
    """
    global _installed
    if _installed:
        return

    from . import (
        components,
        event,
        html,
        loader,
        platform_events,
        po,
        provider,
        sessions,
        star,
        tools,
        web,
    )

    astrbot_mod = ModuleType("astrbot")
    astrbot_mod.__path__ = []
    astrbot_mod.logger = logging.getLogger("astrbot.compat")

    api_mod = ModuleType("astrbot.api")
    api_mod.__path__ = []
    api_mod.logger = astrbot_mod.logger
    api_mod.AstrBotConfig = dict
    api_mod.FunctionTool = tools.FunctionTool
    api_mod.ToolSet = tools.ToolSet
    api_mod.BaseFunctionToolExecutor = type("BaseFunctionToolExecutor", (), {})
    api_mod.llm_tool = event.filter.llm_tool
    api_mod.agent = _unsupported_agent
    api_mod.html_renderer = html.HtmlRendererFacade()
    api_mod.sp = _SharedPreferences()

    event_mod = ModuleType("astrbot.api.event")
    event_mod.__path__ = []
    event_mod.filter = event.filter
    event_mod.AstrMessageEvent = event.AstrMessageEvent
    event_mod.MessageChain = components.MessageChain
    event_mod.MessageEventResult = components.MessageEventResult
    event_mod.ResultContentType = event.ResultContentType
    event_mod.EventResultType = components.EventResultType
    event_mod.CommandResult = components.MessageEventResult

    filter_mod = ModuleType("astrbot.api.event.filter")
    for name in dir(event.filter):
        if not name.startswith("_"):
            setattr(filter_mod, name, getattr(event.filter, name))
    filter_mod.GreedyStr = loader.GreedyStr

    star_mod = ModuleType("astrbot.api.star")
    star_mod.Star = star.Star
    star_mod.Context = star.Context
    star_mod.MessageSesion = star.MessageSesion
    star_mod.StarTools = star.StarTools
    star_mod.register = star.register

    tools_mod = ModuleType("astrbot.core.agent.tool")
    tools_mod.FunctionTool = tools.FunctionTool
    tools_mod.ToolSet = tools.ToolSet
    tools_mod.ToolExecResult = Any

    star_context_mod = ModuleType("astrbot.core.star.context")
    star_context_mod.Context = star.Context

    provider_register_mod = ModuleType("astrbot.core.provider.register")
    provider_register_mod.register_provider = _unsupported("register_provider")
    provider_register_mod.llm_tools = type("llm_tools", (), {})()

    custom_filter_mod = ModuleType("astrbot.core.star.filter.custom_filter")
    custom_filter_mod.CustomFilter = event.CustomFilter

    provider_provider_mod = ModuleType("astrbot.core.provider.provider")
    provider_provider_mod.Provider = provider.Provider
    provider_provider_mod.STTProvider = provider.Provider
    provider_provider_mod.TTSProvider = provider.Provider
    provider_provider_mod.EmbeddingProvider = provider.Provider

    platform_metadata_mod = ModuleType("astrbot.core.platform.platform_metadata")
    platform_metadata_mod.PlatformMetadata = _ShellRecord

    platform_platform_mod = ModuleType("astrbot.core.platform.platform")
    platform_platform_mod.Platform = _ShellRecord
    platform_platform_mod.PlatformStatus = event.PlatformStatus

    config_default_mod = ModuleType("astrbot.core.config.default")
    config_default_mod.DEFAULT_CONFIG = {}
    config_default_mod.CONFIG_METADATA_2 = {}
    config_default_mod.VERSION = host_version or "unknown"

    platform_adapter_type_mod = ModuleType(
        "astrbot.core.star.filter.platform_adapter_type",
    )
    platform_adapter_type_mod.PlatformAdapterType = event.PlatformAdapterType
    platform_adapter_type_mod.PlatformAdapterTypeFilter = (
        event.PlatformAdapterTypeFilter
    )
    platform_adapter_type_mod.ADAPTER_NAME_2_TYPE = {
        name: member for member, name in event.PLATFORM_ADAPTER_NAMES.items()
    }

    star_star_mod = ModuleType("astrbot.core.star.star")
    star_star_mod.Star = star.Star
    star_star_mod.StarMetadata = _ShellRecord
    # Registry introspection is Host-internal; isolated plugins see empty
    # registries (degraded but import-safe).
    star_star_mod.star_map = {}
    star_star_mod.star_registry = []

    run_context_mod = ModuleType("astrbot.core.agent.run_context")
    run_context_mod.ContextWrapper = _ContextWrapper

    agent_context_mod = ModuleType("astrbot.core.astr_agent_context")
    agent_context_mod.AstrAgentContext = _AstrAgentContext

    po_mod = ModuleType("astrbot.core.db.po")
    po_mod.Conversation = po.Conversation
    po_mod.Personality = po.Personality
    po_mod.CronJob = po.CronJob

    register_mod = ModuleType("astrbot.core.star.register")
    register_mod.register_star = star.register
    register_mod.register_llm_tool = event.filter.llm_tool
    register_mod.register_command = event.filter.command
    register_mod.register_command_group = event.filter.command_group
    register_mod.register_regex = event.filter.regex
    register_mod.register_event_message_type = event.filter.event_message_type
    register_mod.register_permission_type = event.filter.permission_type
    register_mod.register_platform_adapter_type = event.filter.platform_adapter_type
    register_mod.register_custom_filter = event.filter.custom_filter
    register_mod.register_agent = _unsupported_agent
    for hook_name in (
        "on_llm_request",
        "on_llm_response",
        "on_decorating_result",
        "after_message_sent",
        "on_waiting_llm_request",
        "on_using_llm_tool",
        "on_llm_tool_respond",
        "on_agent_begin",
        "on_agent_done",
        "on_plugin_error",
        "on_plugin_loaded",
        "on_plugin_unloaded",
        "on_astrbot_loaded",
        "on_platform_loaded",
    ):
        setattr(
            register_mod,
            f"register_{hook_name}",
            getattr(event.filter, hook_name),
        )

    entities_mod = ModuleType("astrbot.core.provider.entities")
    entities_mod.LLMResponse = provider.LLMResponse
    entities_mod.ProviderRequest = provider.ProviderRequest
    entities_mod.ProviderMetaData = provider.ProviderMetaData
    entities_mod.ProviderType = provider.ProviderType
    entities_mod.EmbeddingProvider = provider.Provider
    entities_mod.TokenUsage = _ShellRecord
    entities_mod.ToolCallsResult = _ShellRecord

    conversation_mgr_mod = ModuleType("astrbot.core.conversation_mgr")
    from .conversation import ConversationManager

    conversation_mgr_mod.ConversationManager = ConversationManager
    conversation_mgr_mod.Conversation = po.Conversation

    agent_hooks_mod = ModuleType("astrbot.core.agent.hooks")
    agent_hooks_mod.BaseAgentRunHooks = _ShellRecord

    # Plugins importing CronMessageEvent universally construct it and push it
    # into the Host event queue (event injection), which isolated plugins
    # cannot do. Keep the import working so the plugin loads; constructing the
    # event fails loudly at the injection site.
    class CronMessageEvent:  # noqa: D101
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            from .errors import IsolationUnsupportedError

            raise IsolationUnsupportedError(
                "CronMessageEvent event injection is unavailable in isolated "
                "legacy mode; plugins needing it must run in-process"
            )

    cron_pkg = _namespace_package("astrbot.core.cron")
    cron_events_mod = ModuleType("astrbot.core.cron.events")
    cron_events_mod.CronMessageEvent = CronMessageEvent

    # Same exclusion category: building a Host main agent inside the plugin
    # process (proactive agent turns). Symbols stay importable so the plugin
    # loads; calling them fails loudly.
    tools_pkg = _namespace_package("astrbot.core.tools")
    message_tools_mod = ModuleType("astrbot.core.tools.message_tools")
    message_tools_mod.SendMessageToUserTool = _ShellRecord

    astr_main_agent_mod = ModuleType("astrbot.core.astr_main_agent")
    astr_main_agent_mod.MainAgentBuildConfig = _ShellRecord
    astr_main_agent_mod.build_main_agent = _unsupported(
        "build_main_agent (proactive in-plugin agent)"
    )
    astr_main_agent_mod._get_session_conv = _unsupported(
        "_get_session_conv (proactive in-plugin agent)"
    )

    regex_filter_mod = ModuleType("astrbot.core.star.filter.regex")
    regex_filter_mod.RegexFilter = event.RegexFilter

    message_result_mod = ModuleType("astrbot.core.message.message_event_result")
    message_result_mod.MessageEventResult = components.MessageEventResult
    message_result_mod.MessageChain = components.MessageChain
    message_result_mod.CommandResult = components.MessageEventResult
    message_result_mod.EventResultType = event.EventResultType
    message_result_mod.ResultContentType = event.ResultContentType

    platform_mod = ModuleType("astrbot.core.platform")
    platform_mod.__path__ = []
    platform_mod.AstrMessageEvent = event.AstrMessageEvent
    platform_mod.MessageType = event.MessageType
    platform_mod.MessageMember = event.MessageMember
    platform_mod.AstrBotMessage = event.AstrBotMessage
    platform_mod.Group = event.Group
    platform_mod.PlatformStatus = event.PlatformStatus
    platform_mod.MessageSesion = star.MessageSesion

    # Per-platform source modules legacy plugins import for isinstance
    # checks and raw bot access. Parents up to astrbot.core.platform already
    # resolve; every level below must be pre-registered because the fake
    # packages have an empty __path__.
    platform_sources_mods = {
        "astrbot.core.platform.sources": {},
        "astrbot.core.platform.sources.aiocqhttp": {},
        "astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event": {
            "AiocqhttpMessageEvent": platform_events.AiocqhttpMessageEvent,
        },
        "astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter": {
            "AiocqhttpAdapter": platform_events.AiocqhttpAdapter,
        },
        "astrbot.core.platform.sources.qqofficial": {},
        "astrbot.core.platform.sources.qqofficial.qqofficial_message_event": {
            "QQOfficialMessageEvent": platform_events.QQOfficialMessageEvent,
        },
        "astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter": {
            "QQOfficialPlatformAdapter": platform_events.QQOfficialPlatformAdapter,
        },
        "astrbot.core.platform.sources.qqofficial_webhook": {},
        "astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_event": {
            "QQOfficialWebhookMessageEvent": (
                platform_events.QQOfficialWebhookMessageEvent
            ),
        },
        "astrbot.core.platform.sources.telegram": {},
        "astrbot.core.platform.sources.telegram.tg_event": {
            "TelegramPlatformEvent": platform_events.TelegramPlatformEvent,
        },
        "astrbot.core.platform.sources.lark": {},
        "astrbot.core.platform.sources.lark.lark_event": {
            "LarkMessageEvent": platform_events.LarkMessageEvent,
        },
        "astrbot.core.platform.sources.lark.lark_adapter": {
            "LarkPlatformAdapter": platform_events.LarkPlatformAdapter,
        },
        "astrbot.core.platform.sources.discord": {},
        "astrbot.core.platform.sources.discord.discord_platform_event": {
            "DiscordPlatformEvent": platform_events.DiscordPlatformEvent,
        },
        "astrbot.core.platform.sources.discord.discord_platform_adapter": {
            "DiscordPlatformAdapter": platform_events.DiscordPlatformAdapter,
        },
        "astrbot.core.platform.sources.dingtalk": {},
        "astrbot.core.platform.sources.dingtalk.dingtalk_event": {
            "DingtalkMessageEvent": platform_events.DingtalkMessageEvent,
        },
        "astrbot.core.platform.sources.slack": {},
        "astrbot.core.platform.sources.slack.slack_event": {
            "SlackMessageEvent": platform_events.SlackMessageEvent,
        },
        "astrbot.core.platform.sources.webchat": {},
        "astrbot.core.platform.sources.webchat.webchat_event": {
            "WebChatMessageEvent": platform_events.WebChatMessageEvent,
        },
        "astrbot.core.platform.sources.webchat.webchat_queue_mgr": {
            "webchat_queue_mgr": platform_events.webchat_queue_mgr,
        },
        "astrbot.core.platform.sources.wechatpadpro": {},
        "astrbot.core.platform.sources.wechatpadpro.wechatpadpro_message_event": {
            "WeChatPadProMessageEvent": platform_events.WeChatPadProMessageEvent,
        },
        "astrbot.core.platform.sources.wechatpadpro.wechatpadpro_adapter": {
            "WeChatPadProAdapter": platform_events.WeChatPadProAdapter,
        },
        "astrbot.core.platform.sources.gewechat": {},
        "astrbot.core.platform.sources.gewechat.gewechat_event": {
            "GewechatPlatformEvent": platform_events.GewechatPlatformEvent,
        },
        "astrbot.core.platform.sources.gewechat.client": {
            "SimpleGewechatClient": platform_events.SimpleGewechatClient,
        },
    }
    for sources_name, sources_attrs in platform_sources_mods.items():
        sources_mod = ModuleType(sources_name)
        if not sources_attrs:
            sources_mod.__path__ = []  # mark as package
        for attr_name, attr_value in sources_attrs.items():
            setattr(sources_mod, attr_name, attr_value)
        sys.modules[sources_name] = sources_mod

    command_filter_mod = ModuleType("astrbot.core.star.filter.command")
    command_filter_mod.GreedyStr = loader.GreedyStr
    command_filter_mod.CommandFilter = event.CommandFilter

    permission_mod = ModuleType("astrbot.core.star.filter.permission")
    permission_mod.PermissionType = event.PermissionType
    permission_mod.PermissionTypeFilter = event.PermissionTypeFilter

    event_message_type_mod = ModuleType(
        "astrbot.core.star.filter.event_message_type",
    )
    event_message_type_mod.EventMessageType = event.EventMessageType
    event_message_type_mod.EventMessageTypeFilter = event.EventMessageTypeFilter

    message_components_mod = ModuleType("astrbot.core.message.components")
    message_components_mod.BaseMessageComponent = components.BaseMessageComponent
    for name in (
        "Plain",
        "At",
        "AtAll",
        "Reply",
        "Image",
        "Record",
        "Video",
        "Face",
        "Forward",
        "File",
        "Node",
        "Nodes",
        "Poke",
        "Json",
        "Share",
        "Location",
        "Unknown",
        "ComponentTypes",
    ):
        setattr(message_components_mod, name, getattr(components, name))

    config_mod = _namespace_package("astrbot.core.config")
    config_mod.AstrBotConfig = dict
    astrbot_config_mod = ModuleType("astrbot.core.config.astrbot_config")
    astrbot_config_mod.AstrBotConfig = dict

    core_star_mod = _namespace_package("astrbot.core.star")
    core_star_mod.Star = star.Star
    core_star_mod.Context = star.Context
    core_star_mod.StarTools = star.StarTools
    core_star_mod.register = star.register

    astrbot_message_mod = ModuleType("astrbot.core.platform.astrbot_message")
    astrbot_message_mod.AstrBotMessage = event.AstrBotMessage
    astrbot_message_mod.Group = event.Group
    astrbot_message_mod.PlatformStatus = event.PlatformStatus
    astrbot_message_mod.MessageMember = event.MessageMember
    astrbot_message_mod.MessageType = event.MessageType
    astrbot_message_mod.MessageSesion = star.MessageSesion
    astrbot_message_mod.MessageSession = star.MessageSesion

    message_session_mod = ModuleType("astrbot.core.platform.message_session")
    message_session_mod.MessageSesion = star.MessageSesion
    message_session_mod.MessageSession = star.MessageSesion

    session_waiter_mod = ModuleType("astrbot.core.utils.session_waiter")
    session_waiter_mod.SessionController = sessions.SessionController
    session_waiter_mod.SessionFilter = sessions.SessionFilter
    session_waiter_mod.DefaultSessionFilter = sessions.DefaultSessionFilter
    session_waiter_mod.SessionWaiter = sessions.SessionWaiter
    session_waiter_mod.session_waiter = sessions.session_waiter
    session_waiter_mod.USER_SESSIONS = sessions.USER_SESSIONS
    session_waiter_mod.FILTERS = sessions.FILTERS

    # Old astrbot.api.util re-exported the session waiter trio.
    api_util_mod = ModuleType("astrbot.api.util")
    api_util_mod.SessionController = sessions.SessionController
    api_util_mod.SessionWaiter = sessions.SessionWaiter
    api_util_mod.session_waiter = sessions.session_waiter

    agent_message_mod = ModuleType("astrbot.core.agent.message")
    agent_message_mod.Message = _AgentMessage
    agent_message_mod.ContentPart = _AgentPart
    agent_message_mod.UserMessageSegment = _AgentMessage
    agent_message_mod.AssistantMessageSegment = _AgentMessage
    agent_message_mod.SystemMessageSegment = _AgentMessage
    agent_message_mod.ToolCallMessageSegment = _AgentMessage
    agent_message_mod.TextPart = _AgentPart
    agent_message_mod.ImageURLPart = _AgentPart
    agent_message_mod.AudioURLPart = _AgentPart
    agent_message_mod.ToolCall = _AgentPart

    api_platform_mod = ModuleType("astrbot.api.platform")
    api_platform_mod.AstrBotMessage = event.AstrBotMessage
    api_platform_mod.AstrMessageEvent = event.AstrMessageEvent
    api_platform_mod.Group = event.Group
    api_platform_mod.PlatformStatus = event.PlatformStatus
    api_platform_mod.MessageMember = event.MessageMember
    api_platform_mod.MessageType = event.MessageType
    api_platform_mod.Platform = _ShellRecord
    api_platform_mod.PlatformMetadata = _ShellRecord
    api_platform_mod.register_platform_adapter = _unsupported(
        "register_platform_adapter"
    )
    for name in (
        "BaseMessageComponent",
        "Plain",
        "At",
        "AtAll",
        "Reply",
        "Image",
        "Record",
        "Video",
        "Face",
        "Forward",
        "File",
        "Node",
        "Nodes",
        "Poke",
        "Json",
        "Share",
        "MessageChain",
    ):
        setattr(api_platform_mod, name, getattr(components, name))

    command_group_mod = ModuleType("astrbot.core.star.filter.command_group")
    command_group_mod.CommandGroupFilter = event.CommandFilter

    message_type_mod = ModuleType("astrbot.core.platform.message_type")
    message_type_mod.MessageType = event.MessageType

    astr_message_event_mod = ModuleType(
        "astrbot.core.platform.astr_message_event",
    )
    astr_message_event_mod.AstrMessageEvent = event.AstrMessageEvent
    astr_message_event_mod.MessageSesion = star.MessageSesion
    astr_message_event_mod.MessageSession = star.MessageSesion

    star_tools_mod = ModuleType("astrbot.core.star.star_tools")
    star_tools_mod.StarTools = star.StarTools

    star_handler_mod = ModuleType("astrbot.core.star.star_handler")
    # Registry introspection is Host-internal; isolated plugins see an empty
    # registry (degraded but import-safe).
    star_handler_mod.star_handlers_registry = []
    star_handler_mod.StarHandlerMetadata = _ShellRecord
    star_handler_mod.EventType = _ShellRecord

    astrbot_path_mod = ModuleType("astrbot.core.utils.astrbot_path")

    def _data_path() -> str:
        import os

        return os.environ.get("ASTRBOT_DATA_PATH", ".")

    def _data_subdir(name: str):
        # Mirror astrbot.core.utils.astrbot_path's data-subdirectory helpers;
        # they are plain path derivations, safe to compute inside the Runner.
        def helper() -> str:
            import os

            return os.path.realpath(os.path.join(_data_path(), name))

        return helper

    astrbot_path_mod.get_astrbot_data_path = _data_path
    astrbot_path_mod.get_astrbot_config_path = _data_subdir("config")
    astrbot_path_mod.get_astrbot_plugin_path = _data_subdir("plugins")
    astrbot_path_mod.get_astrbot_plugin_data_path = _data_subdir("plugin_data")
    astrbot_path_mod.get_astrbot_t2i_templates_path = _data_subdir("t2i_templates")
    astrbot_path_mod.get_astrbot_webchat_path = _data_subdir("webchat")
    astrbot_path_mod.get_astrbot_temp_path = _data_subdir("temp")
    astrbot_path_mod.get_astrbot_skills_path = _data_subdir("skills")
    astrbot_path_mod.get_astrbot_workspaces_path = _data_subdir("workspaces")
    astrbot_path_mod.get_astrbot_site_packages_path = _data_subdir("site-packages")
    astrbot_path_mod.get_astrbot_knowledge_base_path = _data_subdir("knowledge_base")
    astrbot_path_mod.get_astrbot_backups_path = _data_subdir("backups")

    def _system_tmp_path() -> str:
        import os
        import tempfile

        return os.path.realpath(os.path.join(tempfile.gettempdir(), ".astrbot"))

    astrbot_path_mod.get_astrbot_system_tmp_path = _system_tmp_path

    provider_mod = ModuleType("astrbot.api.provider")
    provider_mod.LLMResponse = provider.LLMResponse
    provider_mod.Personality = provider.Personality
    provider_mod.Provider = provider.Provider
    provider_mod.ProviderMetaData = provider.ProviderMetaData
    provider_mod.ProviderRequest = provider.ProviderRequest
    provider_mod.ProviderType = provider.ProviderType
    provider_mod.STTProvider = provider.Provider

    components_mod = ModuleType("astrbot.api.message_components")
    for name in (
        "ComponentType",
        "BaseMessageComponent",
        "Plain",
        "At",
        "AtAll",
        "Reply",
        "Image",
        "Record",
        "Video",
        "Face",
        "Forward",
        "File",
        "Node",
        "Nodes",
        "Poke",
        "Json",
        "Share",
        "Location",
        "Unknown",
        "ComponentTypes",
        "MessageChain",
    ):
        setattr(components_mod, name, getattr(components, name))

    message_mod = ModuleType("astrbot.api.message")
    message_mod.MessageEventResult = components.MessageEventResult
    message_mod.MessageChain = components.MessageChain

    web_mod = ModuleType("astrbot.api.web")
    web_mod.request = web.ApiWebRequestProxy()
    web_mod.PluginRequest = web.ApiWebRequestProxy
    web_mod.bind_request_context = web.bind_request_context
    web_mod.PluginMultiDict = web.PluginMultiDict
    web_mod.PluginUploadFile = web.PluginUploadFile
    web_mod.json_response = web.json_response
    web_mod.error_response = web.error_response
    web_mod.file_response = web.file_response
    web_mod.stream_response = web.stream_response
    try:
        from starlette.responses import (
            FileResponse,
            JSONResponse,
            StreamingResponse,
        )

        web_mod.FileResponse = FileResponse
        web_mod.JSONResponse = JSONResponse
        web_mod.StreamingResponse = StreamingResponse
    except ImportError:
        pass

    all_mod = ModuleType("astrbot.api.all")
    all_mod.AstrBotConfig = dict
    all_mod.logger = astrbot_mod.logger
    # The old api.all leaks os into its namespace; plugins star-import it.
    import os as _os

    all_mod.os = _os
    all_mod.html_renderer = html.HtmlRendererFacade()
    all_mod.llm_tool = event_mod.filter.llm_tool
    all_mod.MessageEventResult = components.MessageEventResult
    all_mod.MessageChain = components.MessageChain
    all_mod.CommandResult = components.MessageEventResult
    all_mod.EventResultType = event.EventResultType
    all_mod.AstrMessageEvent = event.AstrMessageEvent
    all_mod.command = event_mod.filter.command
    all_mod.command_group = event_mod.filter.command_group
    all_mod.event_message_type = event_mod.filter.event_message_type
    all_mod.regex = event_mod.filter.regex
    all_mod.platform_adapter_type = event_mod.filter.platform_adapter_type
    all_mod.EventMessageType = event.EventMessageType
    all_mod.EventMessageTypeFilter = event.EventMessageTypeFilter
    all_mod.PlatformAdapterType = event.PlatformAdapterType
    all_mod.PlatformAdapterTypeFilter = event.PlatformAdapterTypeFilter
    all_mod.register = star.register
    all_mod.Context = star.Context
    all_mod.Star = star.Star
    all_mod.Provider = provider.Provider
    all_mod.ProviderMetaData = provider.ProviderMetaData
    all_mod.Personality = po.Personality
    all_mod.AstrBotMessage = event.AstrBotMessage
    all_mod.MessageMember = event.MessageMember
    all_mod.MessageType = event.MessageType
    for name in (
        "BaseMessageComponent",
        "Plain",
        "At",
        "AtAll",
        "Reply",
        "Image",
        "Record",
        "Video",
        "Face",
        "Forward",
        "File",
        "Node",
        "Nodes",
        "Poke",
        "Json",
        "Share",
        "MessageChain",
    ):
        setattr(all_mod, name, getattr(components_mod, name))

    astrbot_mod.api = api_mod
    api_mod.event = event_mod
    api_mod.star = star_mod
    api_mod.provider = provider_mod
    api_mod.message_components = components_mod
    api_mod.message = message_mod
    api_mod.all = all_mod

    sys.modules["astrbot"] = astrbot_mod
    sys.modules["astrbot.api"] = api_mod
    sys.modules["astrbot.api.event"] = event_mod
    sys.modules["astrbot.api.event.filter"] = filter_mod
    sys.modules["astrbot.api.star"] = star_mod
    sys.modules["astrbot.api.provider"] = provider_mod
    sys.modules["astrbot.api.message_components"] = components_mod
    sys.modules["astrbot.api.message"] = message_mod
    sys.modules["astrbot.api.all"] = all_mod
    sys.modules["astrbot.api.web"] = web_mod
    sys.modules["astrbot.api.util"] = api_util_mod

    # Type-only astrbot.core submodules are safe to expose; everything else
    # under astrbot.core stays blocked (live Host internals).
    sys.modules["astrbot.core.agent"] = _namespace_package("astrbot.core.agent")
    sys.modules["astrbot.core.agent.tool"] = tools_mod
    sys.modules["astrbot.core.star.context"] = star_context_mod
    sys.modules["astrbot.core.provider.register"] = provider_register_mod
    sys.modules["astrbot.core.star.filter.custom_filter"] = custom_filter_mod
    sys.modules["astrbot.core.provider.provider"] = provider_provider_mod
    sys.modules["astrbot.core.platform.platform_metadata"] = platform_metadata_mod
    sys.modules["astrbot.core.platform.platform"] = platform_platform_mod
    sys.modules["astrbot.core.config.default"] = config_default_mod
    sys.modules["astrbot.core.star.filter.platform_adapter_type"] = (
        platform_adapter_type_mod
    )
    sys.modules["astrbot.core.star.star"] = star_star_mod
    sys.modules["astrbot.core.agent.run_context"] = run_context_mod
    sys.modules["astrbot.core.astr_agent_context"] = agent_context_mod
    sys.modules["astrbot.core.db"] = _namespace_package("astrbot.core.db")
    sys.modules["astrbot.core.db.po"] = po_mod
    core_provider_pkg = _namespace_package("astrbot.core.provider")
    core_provider_pkg.Provider = provider.Provider
    core_provider_pkg.STTProvider = provider.Provider
    core_provider_pkg.TTSProvider = provider.Provider
    core_provider_pkg.EmbeddingProvider = provider.Provider
    core_provider_pkg.ProviderMetaData = provider.ProviderMetaData
    sys.modules["astrbot.core.provider"] = core_provider_pkg
    sys.modules["astrbot.core.provider.entities"] = entities_mod
    # Some plugins import through the historical "entites" typo path.
    sys.modules["astrbot.core.provider.entites"] = entities_mod
    sys.modules["astrbot.core.conversation_mgr"] = conversation_mgr_mod
    sys.modules["astrbot.core.cron"] = cron_pkg
    sys.modules["astrbot.core.cron.events"] = cron_events_mod
    sys.modules["astrbot.core.tools"] = tools_pkg
    sys.modules["astrbot.core.tools.message_tools"] = message_tools_mod
    sys.modules["astrbot.core.astr_main_agent"] = astr_main_agent_mod
    sys.modules["astrbot.core.agent.hooks"] = agent_hooks_mod
    sys.modules["astrbot.core.star.filter.regex"] = regex_filter_mod
    sys.modules["astrbot.core.message"] = _namespace_package("astrbot.core.message")
    sys.modules["astrbot.core.message.message_event_result"] = message_result_mod
    sys.modules["astrbot.core.platform"] = platform_mod
    sys.modules["astrbot.core.platform.astrbot_message"] = astrbot_message_mod
    sys.modules["astrbot.core.platform.message_session"] = message_session_mod
    sys.modules["astrbot.core.platform.message_type"] = message_type_mod
    sys.modules["astrbot.core.platform.astr_message_event"] = astr_message_event_mod
    sys.modules["astrbot.core.agent.message"] = agent_message_mod
    sys.modules["astrbot.api.platform"] = api_platform_mod
    sys.modules["astrbot.core.star"] = core_star_mod
    sys.modules["astrbot.core.star.star_tools"] = star_tools_mod
    sys.modules["astrbot.core.star.star_handler"] = star_handler_mod
    sys.modules["astrbot.core.star.filter"] = _namespace_package(
        "astrbot.core.star.filter",
    )
    sys.modules["astrbot.core.star.filter.command"] = command_filter_mod
    sys.modules["astrbot.core.star.filter.command_group"] = command_group_mod
    sys.modules["astrbot.core.star.register"] = register_mod
    sys.modules["astrbot.core.star.filter.permission"] = permission_mod
    sys.modules["astrbot.core.star.filter.event_message_type"] = event_message_type_mod
    sys.modules["astrbot.core.message.components"] = message_components_mod
    sys.modules["astrbot.core.config"] = config_mod
    sys.modules["astrbot.core.config.astrbot_config"] = astrbot_config_mod
    sys.modules["astrbot.core.utils"] = _namespace_package("astrbot.core.utils")
    sys.modules["astrbot.core.utils.io"] = _utils_io_mod()
    sys.modules["astrbot.core.utils.session_lock"] = _utils_session_lock_mod()
    sys.modules["astrbot.core.utils.media_utils"] = _utils_media_utils_mod()
    sys.modules["astrbot.core.utils.astrbot_path"] = astrbot_path_mod
    sys.modules["astrbot.core.utils.session_waiter"] = session_waiter_mod
    history_saver_mod = ModuleType("astrbot.core.utils.history_saver")
    history_saver_mod.persist_agent_history = _unsupported(
        "persist_agent_history (proactive in-plugin agent)"
    )
    sys.modules["astrbot.core.utils.history_saver"] = history_saver_mod
    config_number_mod = ModuleType("astrbot.core.utils.config_number")
    from .utils import coerce_int_config

    config_number_mod.coerce_int_config = coerce_int_config
    sys.modules["astrbot.core.utils.config_number"] = config_number_mod

    # Loudly block the real Host internals; the Runner shares the core venv,
    # so astrbot.core would import successfully without this.
    blocked_core = _BlockedModule("astrbot.core")
    # Type-only top-level re-exports stay importable.
    blocked_core.AstrBotConfig = dict
    sys.modules["astrbot.core"] = blocked_core

    _installed = True
