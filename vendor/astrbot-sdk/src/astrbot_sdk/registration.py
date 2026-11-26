from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from .errors import (
    DuplicateHandlerID,
    DuplicateLifecycleHandler,
    InvalidHandlerSignature,
    InvalidPluginDefinition,
)
from .events import MessageType, SenderRole

_HANDLER_SPEC_ATTR = "__astrbot_handler_spec__"
_HANDLER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
HandlerT = TypeVar("HandlerT", bound=Callable[..., Any])


class HandlerKind(StrEnum):
    COMMAND = "command"
    MESSAGE = "message"
    TOOL = "tool"
    SERVICE = "service"
    DIRECT_SERVICE = "direct_service"
    HOOK_LLM_REQUEST = "hook.llm_request"
    HOOK_LLM_RESPONSE = "hook.llm_response"
    HOOK_TOOL_CALL = "hook.tool_call"
    HOOK_TOOL_RESULT = "hook.tool_result"
    HOOK_MESSAGE_RESULT = "hook.message_result"
    HOOK_MESSAGE_SENT = "hook.message_sent"
    HOOK_AGENT_START = "hook.agent_start"
    HOOK_AGENT_END = "hook.agent_end"
    HOOK_WAITING_LLM_REQUEST = "hook.waiting_llm_request"
    HOOK_PLUGIN_ERROR = "hook.plugin_error"
    HOOK_PLUGIN_LOADED = "hook.plugin_loaded"
    HOOK_PLUGIN_UNLOADED = "hook.plugin_unloaded"
    LIFECYCLE_STARTUP = "lifecycle.startup"
    LIFECYCLE_VALIDATE_CONFIG = "lifecycle.validate_config"
    LIFECYCLE_CONFIG_CHANGED = "lifecycle.config_changed"
    LIFECYCLE_HEALTH = "lifecycle.health"
    LIFECYCLE_TOOL_DISCOVERY = "lifecycle.tool_discovery"
    LIFECYCLE_SHUTDOWN = "lifecycle.shutdown"


_LLM_HOOK_STAGES = frozenset(
    {
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "agent_start",
        "agent_end",
        "waiting_llm_request",
        "plugin_error",
    },
)
_PLUGIN_HOOK_STAGES = frozenset({"plugin_loaded", "plugin_unloaded"})
_HOOK_KINDS = frozenset(
    {
        HandlerKind.HOOK_LLM_REQUEST,
        HandlerKind.HOOK_LLM_RESPONSE,
        HandlerKind.HOOK_TOOL_CALL,
        HandlerKind.HOOK_TOOL_RESULT,
        HandlerKind.HOOK_MESSAGE_RESULT,
        HandlerKind.HOOK_MESSAGE_SENT,
        HandlerKind.HOOK_AGENT_START,
        HandlerKind.HOOK_AGENT_END,
        HandlerKind.HOOK_WAITING_LLM_REQUEST,
        HandlerKind.HOOK_PLUGIN_ERROR,
        HandlerKind.HOOK_PLUGIN_LOADED,
        HandlerKind.HOOK_PLUGIN_UNLOADED,
    },
)

_LIFECYCLE_KINDS = frozenset(
    {
        HandlerKind.LIFECYCLE_STARTUP,
        HandlerKind.LIFECYCLE_VALIDATE_CONFIG,
        HandlerKind.LIFECYCLE_CONFIG_CHANGED,
        HandlerKind.LIFECYCLE_HEALTH,
        HandlerKind.LIFECYCLE_TOOL_DISCOVERY,
        HandlerKind.LIFECYCLE_SHUTDOWN,
    }
)
_ONE_PARAM_LIFECYCLE_KINDS = frozenset(
    {
        HandlerKind.LIFECYCLE_STARTUP,
        HandlerKind.LIFECYCLE_HEALTH,
        HandlerKind.LIFECYCLE_TOOL_DISCOVERY,
    }
)


@dataclass(frozen=True, slots=True)
class HandlerSpec:
    kind: HandlerKind
    id: str | None = None
    description: str | None = None
    priority: int = 0
    path: str | None = None
    aliases: tuple[str, ...] = ()
    # Legacy command groups: the handler is a registration anchor only; the
    # host renders the group's usage tree on a bare group-name message.
    group: bool = False
    group_custom_filters: bool = False
    sub_command: bool = False
    tool_name: str | None = None
    resumable: bool = False
    streaming_input: bool = False
    service_name: str | None = None
    direct: bool = False
    input_schema: Mapping[str, Any] | None = None
    message_types: tuple[MessageType, ...] = ()
    platforms: tuple[str, ...] = ()
    roles: tuple[SenderRole, ...] = ()
    regex: str | None = None
    regex_flags: int = 0
    button_action: bool = False
    button_action_id: str | None = None
    ui_action: bool = False
    ui_action_id: str | None = None

    @property
    def required_capability(self) -> str | None:
        if self.kind is HandlerKind.MESSAGE:
            return "message.receive"
        if self.kind is HandlerKind.TOOL:
            return "llm.tool.register"
        if self.kind in _HOOK_KINDS:
            stage = self.kind.value.removeprefix("hook.")
            if stage in _LLM_HOOK_STAGES:
                return "llm.observe"
            if stage in _PLUGIN_HOOK_STAGES:
                return "plugin.inspect"
            return "message.observe"
        return None


@dataclass(frozen=True, slots=True)
class HandlerRegistration:
    id: str
    method_name: str
    spec: HandlerSpec
    handler: Callable[..., Any]


def _normalize_command_path(path: str) -> str:
    normalized = " ".join(path.split())
    if not normalized:
        raise InvalidPluginDefinition("command path cannot be empty")
    return normalized


def _validate_handler_id(handler_id: str | None) -> None:
    if handler_id is not None and not _HANDLER_ID_PATTERN.fullmatch(handler_id):
        raise InvalidPluginDefinition(
            "handler id must start with an alphanumeric character and contain "
            "only letters, numbers, '.', '_' or '-'"
        )


def _attach_handler_spec(
    handler: HandlerT,
    spec: HandlerSpec,
) -> HandlerT:
    if not (
        inspect.iscoroutinefunction(handler) or inspect.isasyncgenfunction(handler)
    ):
        raise InvalidHandlerSignature(
            f"{handler.__qualname__} must be async or an async generator"
        )
    if hasattr(handler, _HANDLER_SPEC_ATTR):
        raise InvalidPluginDefinition(
            f"{handler.__qualname__} can only have one SDK registration decorator"
        )

    parameters = tuple(inspect.signature(handler).parameters.values())
    if not parameters or parameters[0].name != "self":
        raise InvalidHandlerSignature(
            f"{handler.__qualname__} must be an instance method"
        )
    if spec.kind in _LIFECYCLE_KINDS:
        if inspect.isasyncgenfunction(handler):
            raise InvalidHandlerSignature(
                f"{spec.kind.value} handler cannot be an async generator"
            )
        expected_parameters = 1 if spec.kind in _ONE_PARAM_LIFECYCLE_KINDS else 2
        if len(parameters) != expected_parameters:
            raise InvalidHandlerSignature(
                f"{spec.kind.value} handler has an invalid signature"
            )
    if spec.kind in (
        HandlerKind.TOOL,
        HandlerKind.SERVICE,
        HandlerKind.DIRECT_SERVICE,
    ) and inspect.isasyncgenfunction(handler):
        raise InvalidHandlerSignature(
            f"{spec.kind.value} handler cannot be an async generator"
        )
    if spec.kind in _HOOK_KINDS and inspect.isasyncgenfunction(handler):
        raise InvalidHandlerSignature("hook handler cannot be an async generator")

    setattr(handler, _HANDLER_SPEC_ATTR, spec)
    return handler


class _OnNamespace:
    def command(
        self,
        path: str,
        *,
        aliases: Collection[str] = (),
        description: str | None = None,
        message_types: Collection[MessageType] = (),
        platforms: Collection[str] = (),
        roles: Collection[SenderRole] = (),
        priority: int = 0,
        id: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        normalized_path = _normalize_command_path(path)
        normalized_aliases = tuple(_normalize_command_path(alias) for alias in aliases)
        if len(set(normalized_aliases)) != len(normalized_aliases):
            raise InvalidPluginDefinition("command aliases cannot contain duplicates")
        _validate_handler_id(id)

        spec = HandlerSpec(
            kind=HandlerKind.COMMAND,
            id=id,
            description=description,
            priority=priority,
            path=normalized_path,
            aliases=normalized_aliases,
            message_types=tuple(message_types),
            platforms=tuple(platforms),
            roles=tuple(roles),
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def tool(
        self,
        name: str,
        *,
        description: str,
        id: str | None = None,
        resumable: bool = False,
        streaming_input: bool = False,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a static LLM tool handler.

        Args:
            name: Tool name exposed to the LLM.
            description: Tool description shown to the LLM.
            id: Optional stable handler ID within the plugin.
            resumable: Whether external runs may resume across disconnects.
            streaming_input: Whether the tool consumes streamed argument deltas.
        """
        if not name or not name.replace("_", "").isalnum():
            raise InvalidPluginDefinition(
                "tool name must contain only letters, numbers and '_'"
            )
        if not description:
            raise InvalidPluginDefinition("tool description cannot be empty")
        _validate_handler_id(id)
        spec = HandlerSpec(
            kind=HandlerKind.TOOL,
            id=id,
            description=description,
            tool_name=name,
            resumable=resumable,
            streaming_input=streaming_input,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def streaming_tool(
        self,
        name: str,
        *,
        description: str,
        id: str | None = None,
        resumable: bool = False,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a streaming-input LLM tool handler."""
        return self.tool(
            name,
            description=description,
            id=id,
            resumable=resumable,
            streaming_input=True,
        )

    def service(
        self,
        name: str,
        *,
        description: str = "",
        id: str | None = None,
        input_schema: Mapping[str, Any] | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Export a Host-scoped cross-plugin service handler."""
        if not name or not name.replace("_", "").replace("-", "").isalnum():
            raise InvalidPluginDefinition(
                "service name must contain only letters, numbers, '_' and '-'"
            )
        _validate_handler_id(id)
        spec = HandlerSpec(
            kind=HandlerKind.SERVICE,
            id=id or f"service:{name}",
            description=description,
            service_name=name,
            direct=False,
            input_schema=dict(input_schema) if input_schema is not None else None,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def direct_service(
        self,
        name: str,
        *,
        description: str = "",
        id: str | None = None,
        input_schema: Mapping[str, Any] | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Export a revocable direct-mode cross-plugin service handler.

        Direct service handlers execute with `DirectContext` and carry no Host
        or cross-plugin invocation privileges.
        """
        if not name or not name.replace("_", "").replace("-", "").isalnum():
            raise InvalidPluginDefinition(
                "service name must contain only letters, numbers, '_' and '-'"
            )
        _validate_handler_id(id)
        spec = HandlerSpec(
            kind=HandlerKind.DIRECT_SERVICE,
            id=id or f"service:{name}",
            description=description,
            service_name=name,
            direct=True,
            input_schema=dict(input_schema) if input_schema is not None else None,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def tool_discovery(self, handler: HandlerT) -> HandlerT:
        """Register an async method returning dynamic runtime tools."""
        return _attach_handler_spec(
            handler,
            HandlerSpec(kind=HandlerKind.LIFECYCLE_TOOL_DISCOVERY),
        )

    def message(
        self,
        *,
        message_types: Collection[MessageType] = (),
        platforms: Collection[str] = (),
        roles: Collection[SenderRole] = (),
        regex: str | re.Pattern[str] | None = None,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        _validate_handler_id(id)
        regex_pattern: str | None = None
        regex_flags = 0
        if isinstance(regex, re.Pattern):
            regex_pattern = regex.pattern
            regex_flags = regex.flags
        elif regex is not None:
            re.compile(regex)
            regex_pattern = regex

        spec = HandlerSpec(
            kind=HandlerKind.MESSAGE,
            id=id,
            description=description,
            priority=priority,
            message_types=tuple(message_types),
            platforms=tuple(platforms),
            roles=tuple(roles),
            regex=regex_pattern,
            regex_flags=regex_flags,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def button_action(
        self,
        action_id: str | None = None,
        *,
        message_types: Collection[MessageType] = (),
        platforms: Collection[str] = (),
        roles: Collection[SenderRole] = (),
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a handler triggered by callback button interactions."""
        _validate_handler_id(id)
        spec = HandlerSpec(
            kind=HandlerKind.MESSAGE,
            id=id,
            description=description,
            priority=priority,
            message_types=tuple(message_types),
            platforms=tuple(platforms),
            roles=tuple(roles),
            button_action=True,
            button_action_id=action_id,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def ui_action(
        self,
        action_id: str | None = None,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a handler triggered by authenticated ChatUI view actions."""
        _validate_handler_id(id)
        spec = HandlerSpec(
            kind=HandlerKind.MESSAGE,
            id=id,
            description=description,
            priority=priority,
            ui_action=True,
            ui_action_id=action_id,
        )
        return lambda handler: _attach_handler_spec(handler, spec)


def _lifecycle(kind: HandlerKind) -> Callable[[HandlerT], HandlerT]:
    def decorator(handler: HandlerT) -> HandlerT:
        return _attach_handler_spec(handler, HandlerSpec(kind=kind))

    return decorator


def _hook_spec(
    kind: HandlerKind,
    *,
    priority: int,
    id: str | None,
    description: str | None,
) -> HandlerSpec:
    _validate_handler_id(id)
    return HandlerSpec(
        kind=kind,
        id=id,
        description=description,
        priority=priority,
    )


class _HooksNamespace:
    """Namespace for Pipeline hook decorators.

    Each stage has one decorator; hook handlers receive an injected event
    (MessageEvent or None for plugin-initiated calls) plus a mutable
    stage DTO, and return None or a Decision.
    """

    def llm_request(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook before an LLM request is sent."""
        spec = _hook_spec(
            HandlerKind.HOOK_LLM_REQUEST,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def llm_response(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook after an LLM response is received."""
        spec = _hook_spec(
            HandlerKind.HOOK_LLM_RESPONSE,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def tool_call(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook before a tool call executes; may return ToolCallDecision."""
        spec = _hook_spec(
            HandlerKind.HOOK_TOOL_CALL,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def tool_result(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook after a tool call completes."""
        spec = _hook_spec(
            HandlerKind.HOOK_TOOL_RESULT,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def message_result(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook before a message result is sent; may return MessageSendDecision."""
        spec = _hook_spec(
            HandlerKind.HOOK_MESSAGE_RESULT,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def message_sent(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook after a message is sent (observe only)."""
        spec = _hook_spec(
            HandlerKind.HOOK_MESSAGE_SENT,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def agent_start(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook when an agent run starts (observe only)."""
        spec = _hook_spec(
            HandlerKind.HOOK_AGENT_START,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def agent_end(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook when an agent run finishes (observe only)."""
        spec = _hook_spec(
            HandlerKind.HOOK_AGENT_END,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def waiting_llm_request(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook notified before the LLM request lock is acquired (observe only)."""
        spec = _hook_spec(
            HandlerKind.HOOK_WAITING_LLM_REQUEST,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def plugin_error(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook notified when a plugin handler raises during an event."""
        spec = _hook_spec(
            HandlerKind.HOOK_PLUGIN_ERROR,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def plugin_loaded(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook notified after a plugin is loaded."""
        spec = _hook_spec(
            HandlerKind.HOOK_PLUGIN_LOADED,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)

    def plugin_unloaded(
        self,
        *,
        priority: int = 0,
        id: str | None = None,
        description: str | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Hook notified after a plugin is unloaded."""
        spec = _hook_spec(
            HandlerKind.HOOK_PLUGIN_UNLOADED,
            priority=priority,
            id=id,
            description=description,
        )
        return lambda handler: _attach_handler_spec(handler, spec)


hooks = _HooksNamespace()

on = _OnNamespace()


def _description_for(handler: Callable[..., Any]) -> str | None:
    doc = inspect.getdoc(handler)
    if not doc:
        return None
    return " ".join(doc.split("\n\n", 1)[0].splitlines())


def discover_handlers(plugin: object) -> tuple[HandlerRegistration, ...]:
    registrations: list[HandlerRegistration] = []
    ids: set[str] = set()
    lifecycle_kinds: set[HandlerKind] = set()

    for method_name in dir(type(plugin)):
        raw_handler = inspect.getattr_static(type(plugin), method_name)
        spec = getattr(raw_handler, _HANDLER_SPEC_ATTR, None)
        if not isinstance(spec, HandlerSpec):
            continue

        if spec.kind in _LIFECYCLE_KINDS:
            if spec.kind in lifecycle_kinds:
                raise DuplicateLifecycleHandler(
                    f"duplicate lifecycle handler: {spec.kind.value}"
                )
            lifecycle_kinds.add(spec.kind)

        handler_id = (
            spec.kind.value if spec.kind in _LIFECYCLE_KINDS else spec.id or method_name
        )
        if handler_id in ids:
            raise DuplicateHandlerID(f"duplicate handler id: {handler_id}")
        ids.add(handler_id)

        description = spec.description or _description_for(raw_handler)
        resolved_spec = HandlerSpec(
            kind=spec.kind,
            id=handler_id,
            description=description,
            priority=spec.priority,
            path=spec.path,
            aliases=spec.aliases,
            group=spec.group,
            group_custom_filters=spec.group_custom_filters,
            sub_command=spec.sub_command,
            message_types=spec.message_types,
            platforms=spec.platforms,
            roles=spec.roles,
            regex=spec.regex,
            regex_flags=spec.regex_flags,
            button_action=spec.button_action,
            button_action_id=spec.button_action_id,
            ui_action=spec.ui_action,
            ui_action_id=spec.ui_action_id,
            tool_name=spec.tool_name,
            resumable=spec.resumable,
            streaming_input=spec.streaming_input,
            service_name=spec.service_name,
            direct=spec.direct,
            input_schema=spec.input_schema,
        )
        registrations.append(
            HandlerRegistration(
                id=handler_id,
                method_name=method_name,
                spec=resolved_spec,
                handler=getattr(plugin, method_name),
            )
        )

    return tuple(registrations)
