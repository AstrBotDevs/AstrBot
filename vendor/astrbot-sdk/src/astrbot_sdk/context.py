from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Generic, TypeVar

from .capabilities import CapabilitySet
from .conversations import ConversationService
from .errors import (
    CallScopeRetired,
    CapabilityDenied,
    HostUnavailable,
    RemoteError,
    map_remote_error,
)
from .llm import LLMService
from .plugins import PluginRegistryService
from .protocol_registry import register_protocol_dataclass
from .render import RenderService
from .services import AssetService, MessageService, PluginStorage, SessionService
from .tasks import TaskGroup
from .tools import ToolService
from .web import WebService

ConfigT = TypeVar("ConfigT")

_AMBIENT_UMO: ContextVar[Any] = ContextVar("ambient_umo", default=None)
_AMBIENT_EVENT: ContextVar[Any] = ContextVar("ambient_event", default=None)
_AMBIENT_CALL_ID: ContextVar[str | None] = ContextVar("ambient_call_id", default=None)
_ACTIVE_INVOCATION_CTX: ContextVar[PluginContext[Any] | None] = ContextVar(
    "active_invocation_ctx",
    default=None,
)

HostCapabilityInvoker = Callable[
    [str, str, Mapping[str, Any]],
    Awaitable[Any],
]
HostCapabilityStreamInvoker = Callable[
    [str, str, Mapping[str, Any]],
    AsyncIterator[Any],
]
HostServiceInvoker = Callable[
    [str, str, Mapping[str, Any], str | None],
    Awaitable[Any],
]


class RuntimeMode(StrEnum):
    ISOLATED = "isolated"
    IN_PROCESS = "in_process"


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class PluginInfo:
    id: str
    name: str
    version: str
    runtime_mode: RuntimeMode
    author: str | None = None
    desc: str | None = None
    activated: bool = True


@dataclass(slots=True)
class DirectContext(Generic[ConfigT]):
    """Restricted context passed to direct cross-plugin service handlers.

    Exposes only plugin metadata, confirmed configuration, logger, and
    cancellation status — intentionally carrying zero Host or peer authority.
    """

    plugin: PluginInfo
    config: ConfigT
    logger: logging.Logger
    is_cancelled: bool = False
    _config_getter: Callable[[], ConfigT] | None = field(default=None, repr=False)

    def current_config(self) -> ConfigT:
        """Return the latest confirmed configuration snapshot."""
        if self._config_getter is not None:
            return self._config_getter()
        return self.config


@dataclass(slots=True)
class PluginContext(Generic[ConfigT]):
    plugin: PluginInfo
    config: ConfigT
    logger: logging.Logger
    capabilities: CapabilitySet
    data_dir: Path = Path(".")
    storage: PluginStorage = field(init=False)
    messages: MessageService = field(init=False)
    conversations: ConversationService = field(init=False)
    assets: AssetService = field(init=False)
    plugins: PluginRegistryService = field(init=False)
    render: RenderService = field(init=False)
    sessions: SessionService = field(init=False)
    tools: ToolService = field(init=False)
    llm: LLMService = field(init=False)
    web: WebService = field(init=False)
    tasks: TaskGroup = field(default_factory=TaskGroup)
    _host_capability_invoker: HostCapabilityInvoker | None = field(
        default=None,
        repr=False,
    )
    _host_capability_stream_invoker: HostCapabilityStreamInvoker | None = field(
        default=None,
        repr=False,
    )
    _host_service_invoker: HostServiceInvoker | None = field(
        default=None,
        repr=False,
    )
    dynamic_tools: dict[str, Callable[..., Awaitable[Any]]] = field(
        default_factory=dict,
        repr=False,
    )
    cron_handlers: dict[str, Callable[..., Any]] = field(
        default_factory=dict,
        repr=False,
    )
    _session_waiters: dict[str, Any] = field(default_factory=dict, repr=False)
    _parent_call_id: str | None = field(default=None, repr=False)
    _retired: bool = field(default=False, repr=False)
    _root_ctx: PluginContext[ConfigT] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        # Build stable Host service facades. Services never disappear from the
        # context; missing grants surface as CapabilityDenied at call time.
        self.storage = PluginStorage(self, self.data_dir)
        self.messages = MessageService(self)
        self.conversations = ConversationService(self)
        self.assets = AssetService(self)
        self.plugins = PluginRegistryService(self)
        self.render = RenderService(self)
        self.sessions = SessionService(self, waiters=self._session_waiters)
        self.tools = ToolService(self)
        self.llm = LLMService(self)
        self.web = (
            self._root_ctx.web if self._root_ctx is not None else WebService(self)
        )

    def current_config(self) -> ConfigT:
        """Return the latest confirmed configuration snapshot."""
        if self._root_ctx is not None:
            return self._root_ctx.config
        return self.config

    def _update_config(self, new_config: ConfigT) -> None:
        """Apply a confirmed live configuration update."""
        self.config = new_config
        if self._root_ctx is not None:
            self._root_ctx.config = new_config

    def _update_capabilities(self, grants: CapabilitySet) -> None:
        """Atomically replace the plugin's active capability grants."""
        self.capabilities = grants
        if self._root_ctx is not None:
            self._root_ctx.capabilities = grants

    def _retire(self) -> None:
        """Mark this context scope retired so late Host calls fail fast."""
        self._retired = True

    def scoped_for_invocation(self, call_id: str) -> PluginContext[ConfigT]:
        """Return a request-scoped context sharing instance facades under `call_id`."""
        root = self._root_ctx or self
        scoped = PluginContext(
            plugin=root.plugin,
            config=root.config,
            logger=root.logger,
            capabilities=root.capabilities,
            data_dir=root.data_dir,
            tasks=root.tasks,
            _host_capability_invoker=root._host_capability_invoker,
            _host_capability_stream_invoker=root._host_capability_stream_invoker,
            _host_service_invoker=root._host_service_invoker,
            dynamic_tools=root.dynamic_tools,
            cron_handlers=root.cron_handlers,
            _session_waiters=root._session_waiters,
            _parent_call_id=call_id,
            _retired=False,
            _root_ctx=root,
        )
        return scoped

    def direct_view(self, *, is_cancelled: bool = False) -> DirectContext[ConfigT]:
        """Create a DirectContext with zero Host or cross-plugin privileges."""
        root = self._root_ctx or self
        return DirectContext(
            plugin=root.plugin,
            config=root.config,
            logger=root.logger,
            is_cancelled=is_cancelled,
            _config_getter=root.current_config,
        )

    def _register_dynamic_tool(
        self,
        handler_id: str,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        """Register one dynamic tool handler on this context."""
        self.dynamic_tools[handler_id] = handler

    def _unregister_dynamic_tool(self, handler_id: str) -> None:
        """Remove one dynamic tool handler from this context."""
        self.dynamic_tools.pop(handler_id, None)

    async def _invoke_capability(
        self,
        capability_id: str,
        operation: str,
        payload: Mapping[str, Any],
    ) -> Any:
        """Invoke a Host capability for an SDK service implementation.

        Args:
            capability_id: Capability required by the operation.
            operation: Operation within the capability namespace.
            payload: Operation input DTOs.

        Returns:
            Decoded Host response.

        Raises:
            CallScopeRetired: The invocation scope or instance has retired.
            CapabilityDenied: The plugin was not granted the capability.
            HostUnavailable: No Host invocation channel is available.
        """
        if self._retired:
            raise CallScopeRetired("request host scope has retired")
        active_caps = (
            self._root_ctx.capabilities
            if self._root_ctx is not None
            else self.capabilities
        )
        if not active_caps.has(capability_id):
            raise CapabilityDenied(f"capability was not granted: {capability_id}")
        if self._host_capability_invoker is None:
            raise HostUnavailable("Host capability channel is unavailable")
        call_token = (
            _AMBIENT_CALL_ID.set(self._parent_call_id)
            if self._parent_call_id is not None
            else None
        )
        try:
            return await self._host_capability_invoker(
                capability_id,
                operation,
                payload,
            )
        except RemoteError as exc:
            raise map_remote_error(exc) from exc
        finally:
            if call_token is not None:
                _AMBIENT_CALL_ID.reset(call_token)

    def _bind_ambient_umo(self, umo: Any) -> Token:
        """Bind a UMO to the current invocation for provider selection."""
        return _AMBIENT_UMO.set(umo)

    def _reset_ambient_umo(self, token: Token) -> None:
        """Reset the ambient UMO binding."""
        _AMBIENT_UMO.reset(token)

    def _ambient_umo(self) -> Any:
        """Return the UMO bound to the current invocation, if any."""
        return _AMBIENT_UMO.get()

    def _bind_ambient_event(self, event: Any) -> Token:
        """Bind the triggering event to the current invocation."""
        return _AMBIENT_EVENT.set(event)

    def _reset_ambient_event(self, token: Token) -> None:
        """Reset the ambient event binding."""
        _AMBIENT_EVENT.reset(token)

    def _ambient_event(self) -> Any:
        """Return the event bound to the current invocation, if any."""
        return _AMBIENT_EVENT.get()

    def _bind_ambient_call_id(self, call_id: str | None) -> Token:
        """Bind the active invocation call_id for scoped Host calls."""
        return _AMBIENT_CALL_ID.set(call_id)

    def _reset_ambient_call_id(self, token: Token) -> None:
        """Reset the active invocation call_id."""
        _AMBIENT_CALL_ID.reset(token)

    def _ambient_call_id(self) -> str | None:
        """Return the active invocation call_id, if any."""
        return self._parent_call_id or _AMBIENT_CALL_ID.get()

    def _invoke_capability_stream(
        self,
        capability_id: str,
        operation: str,
        payload: Mapping[str, Any],
    ) -> AsyncIterator[Any]:
        """Invoke a Host capability as a flow-controlled stream.

        Args:
            capability_id: Capability required by the operation.
            operation: Operation within the capability namespace.
            payload: Operation input DTOs.

        Returns:
            Async iterator of decoded Host stream items.

        Raises:
            CallScopeRetired: The invocation scope or instance has retired.
            CapabilityDenied: The plugin was not granted the capability.
            HostUnavailable: No Host streaming channel is available.
        """
        if self._retired:
            raise CallScopeRetired("request host scope has retired")
        active_caps = (
            self._root_ctx.capabilities
            if self._root_ctx is not None
            else self.capabilities
        )
        if not active_caps.has(capability_id):
            raise CapabilityDenied(f"capability was not granted: {capability_id}")
        if self._host_capability_stream_invoker is None:
            raise HostUnavailable("Host capability streaming channel is unavailable")
        call_token = (
            _AMBIENT_CALL_ID.set(self._parent_call_id)
            if self._parent_call_id is not None
            else None
        )
        try:
            return self._host_capability_stream_invoker(
                capability_id,
                operation,
                payload,
            )
        finally:
            if call_token is not None:
                _AMBIENT_CALL_ID.reset(call_token)
