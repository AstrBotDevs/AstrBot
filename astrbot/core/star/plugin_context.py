"""Capability-scoped context exposed to Star plugins.

The public plugin SDK deliberately does not expose the core lifecycle, service
locator, database implementation, or mutable runtime catalogs.  The execution
context stays internal; this module adapts its narrowly scoped operations into
plugin-facing capabilities.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from astrbot.core.agent.llm_types import LLMResponse
from astrbot.core.agent.message import Message
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.auth.models import Decision, Resource, Role, Subject
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent, MessageSession
from astrbot.core.platform.onebot_capability import OneBotCapability
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import (
    EmbeddingProvider,
    Provider,
    RerankProvider,
    STTProvider,
    TTSProvider,
)
from astrbot.core.star.command_management import list_commands
from astrbot.core.star.dashboard_extension import DashboardExtensionAccess
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import StarHandlerMetadata
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.io import ensure_dir

if TYPE_CHECKING:
    from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
    from astrbot.core.auth.service import AuthorizationService
    from astrbot.core.conversation_mgr import ConversationManager
    from astrbot.core.cron.manager import CronJobManager
    from astrbot.core.db.protocols import CommandStore, UmoAliasStore
    from astrbot.core.execution_context import CoreExecutionContext
    from astrbot.core.file_token_service import FileTokenService
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.persona_mgr import PersonaManager
    from astrbot.core.provider.manager import ProviderManager
    from astrbot.core.runtime_catalogs import RuntimeCatalogs
    from astrbot.core.utils.shared_preferences import SharedPreferences
    from astrbot.core.utils.t2i.renderer import HtmlRenderer


logger = logging.getLogger("astrbot")
_VT = TypeVar("_VT")


class PluginLifecycleControl(Protocol):
    """Small lifecycle control surface needed by the bundled plugin commands."""

    async def turn_off_plugin(self, plugin_name: str) -> None: ...

    async def turn_on_plugin(self, plugin_name: str) -> None: ...

    async def install_plugin(self, repo_url: str) -> object | None: ...


@dataclass(frozen=True, slots=True)
class PluginInfo:
    """Read-only plugin metadata safe to expose through the SDK."""

    name: str
    author: str
    description: str
    version: str
    active: bool


@dataclass(frozen=True, slots=True)
class PluginCommandInfo:
    """One command belonging to a published plugin."""

    invocation: str
    description: str


@dataclass(frozen=True, slots=True)
class ConversationTokenUsage:
    """Aggregated token usage for one internal-agent conversation."""

    record_count: int
    input_other: int
    input_cached: int
    output: int

    @property
    def total(self) -> int:
        """Return all input and output tokens combined."""
        return self.input_other + self.input_cached + self.output


class MessageCapability:
    """Send messages or submit explicitly constructed inbound events."""

    __slots__ = ("_execution",)

    def __init__(self, execution: CoreExecutionContext) -> None:
        self._execution = execution

    async def send(
        self,
        session: str | MessageSession,
        message_chain: MessageChain,
    ) -> PlatformSendResult:
        """Send a message to one session."""
        return await self._execution.send_message(session, message_chain)

    def submit(self, event: AstrMessageEvent) -> bool:
        """Submit an explicitly constructed event to the bounded event queue."""
        return self._execution.commit_event(event)

    def create_event(
        self,
        platform: str,
        event_message: object,
        *,
        is_wake: bool = True,
    ) -> None:
        """Create and submit an adapter event through its declared platform."""
        self._execution.create_platform_event(
            platform,
            event_message,
            is_wake=is_wake,
        )

    async def wait_for(
        self,
        event: AstrMessageEvent,
        handler: Callable[[Any, AstrMessageEvent], Awaitable[Any]],
        *,
        timeout_seconds: int = 30,
        record_history_chains: bool = False,
    ) -> None:
        """Wait for one later message in the current runtime-owned session."""
        await self._execution.session_waiter_registry.wait_for(
            event,
            handler,
            timeout_seconds=timeout_seconds,
            record_history_chains=record_history_chains,
        )

    async def dispatch_waiter(self, event: AstrMessageEvent) -> bool:
        """Dispatch an inbound event to matching interactive waits."""
        return await self._execution.session_waiter_registry.dispatch(event)


class ModelCapability:
    """Access configured chat-model operations without exposing ProviderManager."""

    __slots__ = ("_provider_manager", "_execution")

    def __init__(
        self,
        execution: CoreExecutionContext,
        provider_manager: ProviderManager,
    ) -> None:
        self._execution = execution
        self._provider_manager = provider_manager

    async def generate(
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
        """Generate one chat completion without executing tool calls."""
        return await self._execution.llm_generate(
            chat_provider_id=chat_provider_id,
            prompt=prompt,
            image_urls=image_urls,
            audio_urls=audio_urls,
            tools=tools,
            system_prompt=system_prompt,
            contexts=contexts,
            **kwargs,
        )

    async def tool_loop(
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
        """Run the bounded tool-loop agent for a plugin-owned request."""
        return await self._execution.tool_loop_agent(
            event=event,
            chat_provider_id=chat_provider_id,
            prompt=prompt,
            image_urls=image_urls,
            audio_urls=audio_urls,
            tools=tools,
            system_prompt=system_prompt,
            contexts=contexts,
            max_steps=max_steps,
            tool_call_timeout=tool_call_timeout,
            **kwargs,
        )

    async def current_chat_provider_id(self, umo: str) -> str:
        """Return the selected chat provider ID for one session."""
        return await self._execution.get_current_chat_provider_id(umo)

    def get(
        self,
        provider_id: str,
    ) -> (
        Provider | TTSProvider | STTProvider | EmbeddingProvider | RerankProvider | None
    ):
        """Return one configured provider instance by ID."""
        return self._execution.get_provider_by_id(provider_id)

    def chat(self) -> tuple[Provider, ...]:
        """Return configured chat providers as an immutable snapshot."""
        return tuple(self._execution.get_all_providers())

    def text_to_speech(self) -> tuple[TTSProvider, ...]:
        """Return configured text-to-speech providers."""
        return tuple(self._execution.get_all_tts_providers())

    def speech_to_text(self) -> tuple[STTProvider, ...]:
        """Return configured speech-to-text providers."""
        return tuple(self._execution.get_all_stt_providers())

    def embeddings(self) -> tuple[EmbeddingProvider, ...]:
        """Return configured embedding providers."""
        return tuple(self._execution.get_all_embedding_providers())

    def using_chat(self, umo: str | None = None) -> Provider | None:
        """Return the active chat provider for a session."""
        return self._execution.get_using_provider(umo)

    def using_text_to_speech(self, umo: str | None = None) -> TTSProvider | None:
        """Return the active text-to-speech provider for a session."""
        return self._execution.get_using_tts_provider(umo)

    def using_speech_to_text(self, umo: str | None = None) -> STTProvider | None:
        """Return the active speech-to-text provider for a session."""
        return self._execution.get_using_stt_provider(umo)

    def configuration(
        self,
        provider_id: str,
        *,
        merged: bool = False,
    ) -> dict | None:
        """Return a provider configuration snapshot for a configured ID."""
        return self._provider_manager.get_provider_config_by_id(
            provider_id,
            merged=merged,
        )

    async def select(
        self,
        *,
        provider_id: str,
        provider_type: ProviderType,
        umo: str | None = None,
    ) -> None:
        """Select a configured provider for a global or session scope."""
        await self._provider_manager.set_provider(
            provider_id=provider_id,
            provider_type=provider_type,
            umo=umo,
        )

    def on_change(
        self,
        callback: Callable[[str, ProviderType, str | None], None],
    ) -> None:
        """Register a local callback for provider selection changes."""
        self._provider_manager.register_provider_change_hook(callback)


class ToolCapability:
    """Manage plugin-owned function tools through the runtime tool catalog."""

    __slots__ = ("_execution",)

    def __init__(self, execution: CoreExecutionContext) -> None:
        self._execution = execution

    def add(self, *tools: FunctionTool) -> None:
        """Publish function tools belonging to the current plugin module."""
        self._execution.add_llm_tools(*tools)

    async def activate(self, name: str) -> bool:
        """Activate one declared function tool."""
        return await self._execution.activate_llm_tool(name)

    async def deactivate(self, name: str) -> bool:
        """Deactivate one declared function tool."""
        return await self._execution.deactivate_llm_tool(name)


class PreferenceCapability:
    """Scope-limited preference operations without exposing the database."""

    __slots__ = ("_preferences",)

    def __init__(self, preferences: SharedPreferences) -> None:
        self._preferences = preferences

    async def session_get(
        self,
        umo: str,
        key: str,
        default: _VT = None,
    ) -> _VT:
        """Read a session-scoped preference."""
        return await self._preferences.session_get(umo, key, default)  # type: ignore[return-value]

    async def session_put(self, umo: str, key: str, value: Any) -> None:
        """Store a session-scoped preference."""
        await self._preferences.session_put(umo, key, value)

    async def session_remove(self, umo: str, key: str) -> None:
        """Remove a session-scoped preference."""
        await self._preferences.session_remove(umo, key)

    async def global_get(self, key: str, default: _VT = None) -> _VT:
        """Read a global preference."""
        return await self._preferences.global_get(key, default)  # type: ignore[return-value]

    async def global_put(self, key: str, value: Any) -> None:
        """Store a global preference."""
        await self._preferences.global_put(key, value)

    async def global_remove(self, key: str) -> None:
        """Remove a global preference."""
        await self._preferences.global_remove(key)


class PluginStorageCapability:
    """Persistent plugin KV data and plugin-owned filesystem paths."""

    __slots__ = ("_preferences", "_catalogs")

    def __init__(
        self,
        preferences: SharedPreferences,
        catalogs: RuntimeCatalogs,
    ) -> None:
        self._preferences = preferences
        self._catalogs = catalogs

    async def get(self, plugin_id: str, key: str, default: _VT = None) -> _VT:
        """Read one key from a plugin's isolated KV namespace."""
        return await self._preferences.get_async("plugin", plugin_id, key, default)

    async def put(self, plugin_id: str, key: str, value: Any) -> None:
        """Store one value in a plugin's isolated KV namespace."""
        await self._preferences.put_async("plugin", plugin_id, key, value)

    async def remove(self, plugin_id: str, key: str) -> None:
        """Delete one key from a plugin's isolated KV namespace."""
        await self._preferences.remove_async("plugin", plugin_id, key)

    def data_directory(self, plugin_name: str | None = None) -> Path:
        """Return and create a dedicated plugin data directory.

        When no plugin name is supplied, the caller's module must belong to a
        currently published plugin.
        """
        if not plugin_name:
            frame = inspect.currentframe()
            try:
                caller = frame.f_back if frame else None
                while caller is not None:
                    module = inspect.getmodule(caller)
                    if module is not None:
                        metadata = self._catalogs.plugins.get_by_module(module.__name__)
                        if metadata is not None and metadata.name:
                            plugin_name = metadata.name
                            break
                    caller = caller.f_back
            finally:
                del frame
            if not plugin_name:
                raise RuntimeError("Unable to resolve caller plugin metadata")

        data_dir = Path(get_astrbot_data_path(), "plugin_data", plugin_name)
        try:
            ensure_dir(data_dir)
        except OSError as exc:
            if isinstance(exc, PermissionError):
                raise RuntimeError(
                    f"Unable to create directory {data_dir}: permission denied",
                ) from exc
            raise RuntimeError(
                f"Unable to create directory {data_dir}: {exc!s}"
            ) from exc
        return data_dir.resolve()


class ConfigurationCapability:
    """Read the resolved configuration for global or session scope."""

    __slots__ = ("_config", "_config_manager")

    def __init__(
        self,
        config: AstrBotConfig,
        config_manager: AstrBotConfigManager,
    ) -> None:
        self._config = config
        self._config_manager = config_manager

    def get(self, umo: str | None = None) -> AstrBotConfig:
        """Return the configuration resolved for an optional session."""
        if not umo:
            return self._config
        return self._config_manager.get_conf(umo)


class ConversationCapability:
    """Conversation operations needed by plugins and bundled command Stars."""

    __slots__ = ("_execution_context", "_manager", "_statistics_store")

    def __init__(
        self,
        execution_context: CoreExecutionContext,
        manager: ConversationManager,
        statistics_store: Any,
    ) -> None:
        self._execution_context = execution_context
        self._manager = manager
        self._statistics_store = statistics_store

    async def current_id(self, umo: str) -> str | None:
        """Return the selected conversation ID for a session."""
        return await self._manager.get_curr_conversation_id(umo)

    async def get(
        self,
        umo: str,
        conversation_id: str,
        *,
        create_if_missing: bool = False,
    ) -> Any:
        """Return a conversation record, optionally creating a replacement."""
        return await self._manager.get_conversation(
            umo,
            conversation_id,
            create_if_not_exists=create_if_missing,
        )

    async def create(
        self,
        umo: str,
        platform_id: str | None = None,
        *,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> str:
        """Create and select a conversation for a session."""
        return await self._manager.new_conversation(
            umo,
            platform_id,
            content=content,
            title=title,
            persona_id=persona_id,
        )

    async def update(
        self,
        umo: str,
        *,
        conversation_id: str | None = None,
        history: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
        token_usage: int | None = None,
    ) -> None:
        """Update one conversation selected by ID or current session state."""
        await self._manager.update_conversation(
            umo,
            conversation_id,
            history,
            title,
            persona_id,
            token_usage,
        )

    async def switch(self, umo: str, conversation_id: str) -> None:
        """Select an existing conversation for a session."""
        await self._manager.switch_conversation(umo, conversation_id)

    async def delete(
        self,
        umo: str,
        conversation_id: str | None = None,
    ) -> None:
        """Delete a conversation from a session."""
        await self._manager.delete_conversation(umo, conversation_id)

    def stop_active_events(
        self,
        umo: str,
        *,
        exclude: AstrMessageEvent | None = None,
    ) -> int:
        """Stop all active events for a session except an optional command event."""
        return self._execution_context.active_event_registry.stop_all(
            umo,
            exclude=exclude,
        )

    def request_agent_stop_all(
        self,
        umo: str,
        *,
        exclude: AstrMessageEvent | None = None,
    ) -> int:
        """Request cooperative Agent cancellation for every event in a session."""
        return self._execution_context.active_event_registry.request_agent_stop_all(
            umo,
            exclude=exclude,
        )

    async def list(
        self, umo: str | None = None, platform_id: str | None = None
    ) -> list[Any]:
        """Return conversation records matching a session or platform."""
        return await self._manager.get_conversations(umo, platform_id)

    async def readable_history(
        self,
        umo: str,
        conversation_id: str,
        *,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[str], int]:
        """Return paged human-readable conversation history."""
        return await self._manager.get_human_readable_context(
            umo,
            conversation_id,
            page,
            page_size,
        )

    async def token_usage(self, conversation_id: str) -> ConversationTokenUsage:
        """Return aggregate model token usage for one conversation.

        The SQL session remains internal to this capability.  Plugins receive
        only the aggregate values needed for display or accounting.
        """
        from sqlalchemy import case, func, select
        from sqlmodel import col

        from astrbot.core.db.po import ProviderStat

        async with self._statistics_store.get_db() as session:
            result = await session.execute(
                select(
                    func.count(case((col(ProviderStat.id).is_not(None), 1))).label(
                        "record_count",
                    ),
                    func.coalesce(func.sum(ProviderStat.token_input_other), 0).label(
                        "total_input_other",
                    ),
                    func.coalesce(func.sum(ProviderStat.token_input_cached), 0).label(
                        "total_input_cached",
                    ),
                    func.coalesce(func.sum(ProviderStat.token_output), 0).label(
                        "total_output",
                    ),
                ).where(
                    col(ProviderStat.agent_type) == "internal",
                    col(ProviderStat.conversation_id) == conversation_id,
                )
            )
            stats = result.one()
        return ConversationTokenUsage(
            record_count=int(stats.record_count or 0),
            input_other=int(stats.total_input_other or 0),
            input_cached=int(stats.total_input_cached or 0),
            output=int(stats.total_output or 0),
        )


class PersonaCapability:
    """Read and select personas without exposing PersonaManager."""

    __slots__ = ("_manager",)

    def __init__(self, manager: PersonaManager) -> None:
        self._manager = manager

    async def default(self, umo: str | MessageSession | None = None) -> Any:
        """Return the configured default runtime persona."""
        return await self._manager.get_default_runtime_persona(umo)

    def get(self, persona_id: str | None) -> Any:
        """Return one runtime persona by identifier."""
        return self._manager.get_runtime_persona_by_id(persona_id)

    async def folders(self) -> list[dict]:
        """Return the current persona folder hierarchy."""
        return await self._manager.get_folder_tree()

    def all(self) -> tuple[Any, ...]:
        """Return an immutable snapshot of configured personas."""
        return tuple(self._manager.personas)

    async def resolve(
        self,
        *,
        umo: str,
        conversation_persona_id: str | None,
        platform_name: str,
        provider_settings: dict,
    ) -> tuple[str | None, Any, str | None, Any]:
        """Resolve the effective persona under session routing rules."""
        return await self._manager.resolve_selected_persona(
            umo=umo,
            conversation_persona_id=conversation_persona_id,
            platform_name=platform_name,
            provider_settings=provider_settings,
        )


class CronCapability:
    """Schedule and inspect cron jobs through the managed cron runtime."""

    __slots__ = ("_manager",)

    def __init__(self, manager: CronJobManager) -> None:
        self._manager = manager

    async def add_basic(self, **kwargs: Any) -> Any:
        """Add a plugin-owned basic cron job."""
        return await self._manager.add_basic_job(**kwargs)

    async def add_active(self, **kwargs: Any) -> Any:
        """Add an active-agent cron job."""
        return await self._manager.add_active_job(**kwargs)

    async def update(self, job_id: str, **kwargs: Any) -> Any:
        """Update one cron job."""
        return await self._manager.update_job(job_id, **kwargs)

    async def delete(self, job_id: str) -> None:
        """Delete one cron job."""
        await self._manager.delete_job(job_id)

    async def list(self, job_type: str | None = None) -> list[Any]:
        """List cron jobs visible to the runtime."""
        return await self._manager.list_jobs(job_type)

    async def run_now(self, job_id: str) -> None:
        """Run one cron job immediately."""
        await self._manager.run_job_now(job_id)


class KnowledgeCapability:
    """Knowledge-base operations exposed as a constrained facade."""

    __slots__ = ("_manager",)

    def __init__(self, manager: KnowledgeBaseManager) -> None:
        self._manager = manager

    async def list(self) -> list[Any]:
        """List available knowledge bases."""
        return await self._manager.list_kbs()

    async def retrieve(
        self,
        query: str,
        knowledge_base_names: list[str],
        *,
        top_k_fusion: int = 20,
        top_m_final: int = 5,
    ) -> dict | None:
        """Retrieve grounded context from named knowledge bases."""
        return await self._manager.retrieve(
            query,
            knowledge_base_names,
            top_k_fusion=top_k_fusion,
            top_m_final=top_m_final,
        )


class PlatformActionsCapability:
    """Invoke explicitly declared proactive platform actions."""

    __slots__ = ("_execution",)

    def __init__(self, execution: CoreExecutionContext) -> None:
        self._execution = execution

    async def invoke(
        self,
        platform_id: str,
        action_name: str,
        **kwargs: Any,
    ) -> dict[str, object]:
        """Invoke a declared action for a platform adapter."""
        return await self._execution.invoke_platform_action(
            platform_id,
            action_name,
            **kwargs,
        )

    async def invoke_for_event(
        self,
        event: AstrMessageEvent,
        action_name: str,
        **kwargs: Any,
    ) -> dict[str, object]:
        """Invoke a declared action for the event's source adapter."""
        return await self._execution.invoke_event_platform_action(
            event,
            action_name,
            **kwargs,
        )


class RenderingCapability:
    """Render HTML and text through the managed renderer."""

    __slots__ = ("_renderer",)

    def __init__(self, renderer: HtmlRenderer) -> None:
        self._renderer = renderer

    async def text_to_image(
        self,
        text: str,
        *,
        template_name: str | None = None,
    ) -> str:
        """Render text using the configured text-to-image template."""
        return await self._renderer.render_t2i(text, template_name=template_name)

    async def html(
        self,
        template: str,
        data: dict,
        *,
        options: dict | None = None,
    ) -> str:
        """Render a custom HTML template to an image."""
        return await self._renderer.render_custom_template(
            template,
            data,
            options=options,
        )


class FileCapability:
    """Publish temporary files through short-lived Dashboard file tokens."""

    __slots__ = ("_file_token_service",)

    def __init__(self, file_token_service: FileTokenService) -> None:
        self._file_token_service = file_token_service

    async def publish(self, file_path: str, *, ttl_seconds: float | None = None) -> str:
        """Publish a local file and return its short-lived token."""
        return await self._file_token_service.register_file(file_path, ttl_seconds)


class SessionCapability:
    """Read and update UMO aliases without exposing a database session."""

    __slots__ = ("_store",)

    def __init__(self, store: UmoAliasStore) -> None:
        self._store = store

    async def alias(self, umo: str) -> Any:
        """Return the optional display alias for one UMO."""
        return await self._store.get_umo_alias(umo)

    async def set_alias(
        self,
        *,
        umo: str,
        creator_sender_id: str,
        auto_name: str | None,
        user_alias: str | None,
    ) -> Any:
        """Create or update the display alias for one UMO."""
        return await self._store.upsert_umo_alias(
            umo=umo,
            creator_sender_id=creator_sender_id,
            auto_name=auto_name,
            user_alias=user_alias,
        )


class AuthorizationCapability:
    """Event-bound authorization access without exposing database tables."""

    __slots__ = (
        "_authorization",
        "_plugin_id",
        "_declared_actions",
        "_allow_core_actions",
    )

    def __init__(
        self,
        authorization: AuthorizationService | None,
        *,
        plugin_id: str | None = None,
        declared_actions: frozenset[str] = frozenset(),
        allow_core_actions: bool = False,
    ) -> None:
        self._authorization = authorization
        self._plugin_id = plugin_id
        self._declared_actions = declared_actions
        self._allow_core_actions = allow_core_actions

    def for_plugin(
        self,
        plugin_id: str,
        declared_actions: frozenset[str],
        *,
        allow_core_actions: bool = False,
    ) -> AuthorizationCapability:
        """Return a plugin-bound view limited to declared plugin actions."""

        return AuthorizationCapability(
            self._authorization,
            plugin_id=plugin_id,
            declared_actions=declared_actions,
            allow_core_actions=allow_core_actions,
        )

    async def authorize(
        self,
        event: AstrMessageEvent,
        action: str,
        resource: Resource | None = None,
    ) -> Decision:
        """Authorize an event's trusted actor against an explicit resource."""

        if self._plugin_id is not None and not self._allow_core_actions:
            if (
                not action.startswith("plugin:")
                or action not in self._declared_actions
                or not action.startswith(f"plugin:{self._plugin_id}:")
            ):
                raise PermissionError("Plugin action is not declared by this plugin")
        if (
            self._authorization is None
            or event.subject is None
            or event.resource is None
            or event.auth_context is None
        ):
            raise PermissionError("Authorization context is unavailable")
        return await self._authorization.authorize(
            event.subject,
            action,
            resource or event.resource,
            event.auth_context,
        )

    async def authorize_target_session(
        self,
        event: AstrMessageEvent,
        *,
        action: str,
        umo: str,
    ) -> Decision:
        """Authorize an explicit cross-session operation against its target.

        Session facts attached to the inbound event are only valid for the
        inbound resource. Clearing them prevents a command argument from
        inheriting the caller's owner/admin fact or member fallback.
        """

        if self._plugin_id is not None and not self._allow_core_actions:
            if (
                not action.startswith("plugin:")
                or action not in self._declared_actions
                or not action.startswith(f"plugin:{self._plugin_id}:")
            ):
                raise PermissionError("Plugin action is not declared by this plugin")
        if (
            self._authorization is None
            or event.subject is None
            or event.auth_context is None
            or not event.auth_context.config_id
        ):
            raise PermissionError("Authorization context is unavailable")
        target = Resource.session(event.auth_context.config_id, umo)
        target_context = replace(
            event.auth_context,
            origin_session_resource_id=None,
            platform_member_role="unknown",
            platform_role_source="none",
            platform_role_expires_at=None,
        )
        return await self._authorization.authorize(
            event.subject,
            action,
            target,
            target_context,
        )

    def session_resource(
        self, event: AstrMessageEvent, *, umo: str | None = None
    ) -> Resource:
        """Build a config-scoped session resource from a trusted event context."""

        if event.auth_context is None or not event.auth_context.config_id:
            raise PermissionError("Authorization context is unavailable")
        return Resource.session(
            event.auth_context.config_id, umo or event.unified_msg_origin
        )

    async def list_bindings(self, event: AstrMessageEvent) -> list[object]:
        """List bindings visible to the caller's authorized scope.

        Session owners may inspect the bindings for their current session, while
        instance operators and Dashboard control-plane identities may inspect
        the bindings in their authorized configuration scope.  Do not widen a
        session owner's read to every session in the configuration.
        """

        if self._plugin_id is not None and not self._allow_core_actions:
            raise PermissionError("Plugin cannot manage authorization bindings")
        decision = await self.authorize(event, "identity.manage")
        if not decision.allowed:
            raise PermissionError("Authorization denied")
        assert self._authorization is not None
        bindings = await self._authorization.list_bindings(
            config_id=event.auth_context.config_id
        )
        if decision.effective_role is Role.SESSION_OWNER:
            if event.resource is None or event.resource.type != "session":
                raise PermissionError("Authorization context is unavailable")
            return [
                binding
                for binding in bindings
                if binding.scope_type == "session"
                and binding.scope_id == event.resource.id
            ]
        return bindings

    async def grant_session_admin(
        self, event: AstrMessageEvent, target_sender_id: str
    ) -> object:
        """Grant only a current-session administrator binding."""

        if self._plugin_id is not None and not self._allow_core_actions:
            raise PermissionError("Plugin cannot manage authorization bindings")
        decision = await self.authorize(event, "identity.manage")
        if not decision.allowed:
            raise PermissionError("Authorization denied")
        assert self._authorization is not None
        assert event.resource is not None
        target = Subject.im(
            platform_instance=event.get_platform_id(),
            bot_account_id=event.get_self_id() or "default",
            sender_id=target_sender_id,
        )
        return await self._authorization.grant_binding(
            actor=event.subject,
            subject_id=target.id,
            role=Role.SESSION_ADMIN,
            scope_type="session",
            scope_id=event.resource.id,
            config_id=event.resource.config_id,
            context=event.auth_context,
        )

    async def revoke_session_admin(
        self, event: AstrMessageEvent, target_sender_id: str
    ) -> bool:
        """Revoke a current-session administrator binding if one exists."""

        if self._plugin_id is not None and not self._allow_core_actions:
            raise PermissionError("Plugin cannot manage authorization bindings")
        decision = await self.authorize(event, "identity.manage")
        if not decision.allowed:
            raise PermissionError("Authorization denied")
        assert self._authorization is not None
        assert event.resource is not None
        target = Subject.im(
            platform_instance=event.get_platform_id(),
            bot_account_id=event.get_self_id() or "default",
            sender_id=target_sender_id,
        )
        bindings = await self._authorization.list_bindings(subject_id=target.id)
        for binding in bindings:
            if (
                getattr(binding, "role", None) == Role.SESSION_ADMIN.value
                and getattr(binding, "scope_id", None) == event.resource.id
            ):
                return await self._authorization.revoke_binding(
                    actor=event.subject,
                    binding_id=getattr(binding, "binding_id"),
                    context=event.auth_context,
                )
        return False


class RuntimeInfoCapability:
    """Read runtime metadata and invoke the narrow plugin lifecycle controls."""

    __slots__ = ("_catalogs", "_command_store", "_demo_mode", "_plugin_control")

    def __init__(
        self,
        catalogs: RuntimeCatalogs,
        command_store: CommandStore,
        *,
        demo_mode: bool,
    ) -> None:
        self._catalogs = catalogs
        self._command_store = command_store
        self._demo_mode = demo_mode
        self._plugin_control: PluginLifecycleControl | None = None

    @property
    def demo_mode(self) -> bool:
        """Whether this runtime is running in restricted demo mode."""
        return self._demo_mode

    def plugins(self) -> tuple[PluginInfo, ...]:
        """Return a read-only snapshot of published plugins."""
        return tuple(
            self._to_plugin_info(metadata) for metadata in self._catalogs.plugins
        )

    def plugin(self, name: str) -> PluginInfo | None:
        """Return read-only metadata for a named plugin."""
        metadata = self._catalogs.plugins.get_by_name(name)
        return self._to_plugin_info(metadata) if metadata is not None else None

    async def commands(self) -> list[dict]:
        """Return the resolved command tree without exposing command storage."""
        return await list_commands(self._command_store, self._catalogs.handlers)

    def commands_for_plugin(self, plugin_name: str) -> tuple[PluginCommandInfo, ...]:
        """Return formatted command invocations declared by one plugin."""
        metadata = self._catalogs.plugins.get_by_name(plugin_name)
        if metadata is None or metadata.module_path is None:
            return ()

        entries: list[PluginCommandInfo] = []
        for handler in self._catalogs.handlers:
            if not isinstance(handler, StarHandlerMetadata):
                continue
            if handler.handler_module_path != metadata.module_path:
                continue
            for filter_ in handler.event_filters:
                if not isinstance(filter_, (CommandFilter, CommandGroupFilter)):
                    continue
                command_names = filter_.get_complete_command_names()
                if not command_names:
                    continue
                entries.append(
                    PluginCommandInfo(
                        invocation=filter_.format_invocation(
                            command_name=command_names[0],
                            include_aliases=True,
                        ),
                        description=handler.desc or "",
                    ),
                )
                break
        return tuple(sorted(entries, key=lambda item: item.invocation.lower()))

    def _bind_plugin_control(self, control: PluginLifecycleControl) -> None:
        """Attach the internal lifecycle port after PluginManager construction."""
        self._plugin_control = control

    async def enable_plugin(self, plugin_name: str) -> None:
        """Enable a plugin through the runtime's lifecycle owner."""
        await self._require_plugin_control().turn_on_plugin(plugin_name)

    async def disable_plugin(self, plugin_name: str) -> None:
        """Disable a plugin through the runtime's lifecycle owner."""
        await self._require_plugin_control().turn_off_plugin(plugin_name)

    async def install_plugin(self, repo_url: str) -> None:
        """Install a plugin through the runtime's lifecycle owner."""
        await self._require_plugin_control().install_plugin(repo_url)

    def _require_plugin_control(self) -> PluginLifecycleControl:
        if self._plugin_control is None:
            raise RuntimeError("Plugin lifecycle control is not available")
        return self._plugin_control

    @staticmethod
    def _to_plugin_info(metadata: StarMetadata) -> PluginInfo:
        return PluginInfo(
            name=metadata.name or "",
            author=metadata.author or "",
            description=metadata.desc or "",
            version=metadata.version or "",
            active=metadata.activated,
        )


class PluginContext:
    """Public, capability-scoped context passed to every :class:`Star`.

    The context intentionally owns no mutable registrations and does not
    expose core managers, a lifecycle object, or database access.  Each field
    is a narrow capability façade with a stable plugin-facing purpose.
    """

    __slots__ = (
        "messages",
        "models",
        "tools",
        "storage",
        "preferences",
        "config",
        "conversations",
        "personas",
        "cron",
        "knowledge",
        "platform_actions",
        "onebot",
        "dashboard_extensions",
        "runtime_info",
        "rendering",
        "files",
        "sessions",
        "authz",
    )

    def __init__(
        self,
        *,
        messages: MessageCapability,
        models: ModelCapability,
        tools: ToolCapability,
        storage: PluginStorageCapability,
        preferences: PreferenceCapability,
        config: ConfigurationCapability,
        conversations: ConversationCapability,
        personas: PersonaCapability,
        cron: CronCapability,
        knowledge: KnowledgeCapability,
        platform_actions: PlatformActionsCapability,
        onebot: OneBotCapability,
        dashboard_extensions: DashboardExtensionAccess,
        runtime_info: RuntimeInfoCapability,
        rendering: RenderingCapability,
        files: FileCapability,
        sessions: SessionCapability,
        authz: AuthorizationCapability,
    ) -> None:
        self.messages = messages
        self.models = models
        self.tools = tools
        self.storage = storage
        self.preferences = preferences
        self.config = config
        self.conversations = conversations
        self.personas = personas
        self.cron = cron
        self.knowledge = knowledge
        self.platform_actions = platform_actions
        self.onebot = onebot
        self.dashboard_extensions = dashboard_extensions
        self.runtime_info = runtime_info
        self.rendering = rendering
        self.files = files
        self.sessions = sessions
        self.authz = authz

    @classmethod
    def from_execution_context(cls, execution: CoreExecutionContext) -> PluginContext:
        """Build the public SDK façade from the internal execution context.

        This is the only bridge that knows both sides of the boundary.  The
        resulting object retains capability facades only, never the execution
        context itself.
        """
        catalogs = execution.catalogs
        return cls(
            messages=MessageCapability(execution),
            models=ModelCapability(execution, execution.provider_manager),
            tools=ToolCapability(execution),
            storage=PluginStorageCapability(execution.preferences, catalogs),
            preferences=PreferenceCapability(execution.preferences),
            config=ConfigurationCapability(
                execution._config,
                execution.astrbot_config_mgr,
            ),
            conversations=ConversationCapability(
                execution,
                execution.conversation_manager,
                execution.database,
            ),
            personas=PersonaCapability(execution.persona_manager),
            cron=CronCapability(execution.cron_manager),
            knowledge=KnowledgeCapability(execution.kb_manager),
            platform_actions=PlatformActionsCapability(execution),
            onebot=OneBotCapability(execution),
            dashboard_extensions=execution.dashboard_extensions,
            runtime_info=RuntimeInfoCapability(
                catalogs,
                execution.database,
                demo_mode=execution.demo_mode,
            ),
            rendering=RenderingCapability(execution.html_renderer),
            files=FileCapability(execution.file_token_service),
            sessions=SessionCapability(execution.database),
            authz=AuthorizationCapability(getattr(execution, "authorization", None)),
        )

    def _bind_plugin_lifecycle_control(self, control: PluginLifecycleControl) -> None:
        """Bind internal plugin lifecycle control during runtime construction."""
        self.runtime_info._bind_plugin_control(control)

    def for_plugin(
        self,
        plugin_id: str,
        declared_actions: frozenset[str],
        *,
        allow_core_actions: bool = False,
    ) -> PluginContext:
        """Create a plugin-scoped SDK view with a restricted authz capability."""

        return PluginContext(
            messages=self.messages,
            models=self.models,
            tools=self.tools,
            storage=self.storage,
            preferences=self.preferences,
            config=self.config,
            conversations=self.conversations,
            personas=self.personas,
            cron=self.cron,
            knowledge=self.knowledge,
            platform_actions=self.platform_actions,
            onebot=self.onebot,
            dashboard_extensions=self.dashboard_extensions,
            runtime_info=self.runtime_info,
            rendering=self.rendering,
            files=self.files,
            sessions=self.sessions,
            authz=self.authz.for_plugin(
                plugin_id,
                declared_actions,
                allow_core_actions=allow_core_actions,
            ),
        )

    def _rebind_runtime_catalogs(self, catalogs: RuntimeCatalogs) -> None:
        """Move a staged context's catalog-facing capabilities to live state.

        Plugin reload initializes a replacement against isolated catalogs. Once
        that generation is published, only these two capability facades retain
        a direct catalog reference; the remaining facades call their execution
        context and therefore follow its live catalog assignment.
        """
        self.storage._catalogs = catalogs
        self.runtime_info._catalogs = catalogs


__all__ = [
    "ConfigurationCapability",
    "ConversationTokenUsage",
    "ConversationCapability",
    "CronCapability",
    "FileCapability",
    "KnowledgeCapability",
    "MessageCapability",
    "ModelCapability",
    "PersonaCapability",
    "PlatformActionsCapability",
    "OneBotCapability",
    "PluginCommandInfo",
    "PluginContext",
    "PluginInfo",
    "PluginLifecycleControl",
    "PluginStorageCapability",
    "PreferenceCapability",
    "RenderingCapability",
    "RuntimeInfoCapability",
    "SessionCapability",
    "ToolCapability",
]
