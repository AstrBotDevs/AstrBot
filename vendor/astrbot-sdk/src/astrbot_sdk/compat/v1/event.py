"""Legacy AstrMessageEvent facade and the filter decorator namespace."""

from __future__ import annotations

import asyncio
import enum
import logging
import os
import re
from typing import Any

from ...events import MessageEvent, SenderRole
from ...results import Propagation
from .components import (
    ButtonInteraction,
    Image,
    MessageChain,
    MessageEventResult,
    Plain,
    UIInteraction,
    from_sdk_segment,
)
from .components import (
    EventResultType as EventResultType,
)
from .components import (
    ResultContentType as ResultContentType,
)

logger = logging.getLogger(__name__)

# Marker attribute where compat filter decorators accumulate their specs.
_FILTERS_ATTR = "__astrbot_compat_filters__"


def _accumulate(handler: Any, filter_spec: Any) -> Any:
    filters = getattr(handler, _FILTERS_ATTR, None)
    if filters is None:
        filters = []
        setattr(handler, _FILTERS_ATTR, filters)
    filters.append(filter_spec)
    return handler


class CommandFilter:
    def __init__(
        self,
        command_name: str,
        alias: set | None = None,
        is_group: bool = False,
        is_sub_command: bool = False,
        priority: int | None = None,
    ) -> None:
        self.command_name = command_name
        self.alias = alias or set()
        # Group anchors render the usage tree on a bare group-name message
        # (in-process CommandGroupFilter) instead of running the handler.
        self.is_group = is_group
        self.is_sub_command = is_sub_command
        self.priority = priority


class RegexFilter:
    def __init__(self, regex: str, priority: int | None = None) -> None:
        self.regex = regex
        self.priority = priority


class EventMessageTypeFilter:
    def __init__(
        self,
        event_message_type: Any,
        priority: int | None = None,
    ) -> None:
        self.event_message_type = event_message_type
        self.priority = priority


class PermissionTypeFilter:
    def __init__(
        self,
        permission_type: Any,
        raise_error: bool = True,
        priority: int | None = None,
    ) -> None:
        self.permission_type = permission_type
        self.raise_error = raise_error
        self.priority = priority

    def filter(self, event: Any, cfg: Any = None) -> bool:
        """Runtime permission check, mirroring the in-process filter."""
        del cfg
        if self.permission_type & PermissionType.ADMIN or (
            self.permission_type & PermissionType.GROUP_ADMIN and event.get_group_id()
        ):
            return bool(event.is_admin())
        return True


class PlatformAdapterTypeFilter:
    def __init__(
        self,
        platform_adapter_type_or_str: Any,
        priority: int | None = None,
    ) -> None:
        self.platform_type = platform_adapter_type_or_str
        self.priority = priority


class CustomFilter:
    """Marker for legacy custom filters.

    The old core instantiates the filter class with a single positional
    argument (its raise_error slot, default True); already-instantiated
    filters are used as-is.
    """

    def __init__(
        self,
        custom_filter: Any,
        *args: Any,
        priority: int | None = None,
    ) -> None:
        if isinstance(custom_filter, type):
            custom_filter = custom_filter(args[0] if args else True)
        self.custom_filter = custom_filter
        self.priority = priority


class ButtonActionFilter:
    """Filter matching normalized callback button interaction events."""

    def __init__(
        self,
        action_id: str | None = None,
        priority: int | None = None,
    ) -> None:
        self.action_id = action_id
        self.priority = priority

    def filter(self, event: Any, cfg: Any = None) -> bool:
        del cfg
        interaction = (
            event.get_button_interaction()
            if hasattr(event, "get_button_interaction")
            else None
        )
        if interaction is None:
            return False
        return self.action_id is None or interaction.action_id == self.action_id


class UIActionFilter:
    """Filter matching authenticated ChatUI view interaction events."""

    def __init__(
        self,
        action_id: str | None = None,
        priority: int | None = None,
    ) -> None:
        self.action_id = action_id
        self.priority = priority

    def filter(self, event: Any, cfg: Any = None) -> bool:
        del cfg
        interaction = (
            event.get_ui_interaction() if hasattr(event, "get_ui_interaction") else None
        )
        if interaction is None:
            return False
        return self.action_id is None or interaction.action_id == self.action_id


class _CommandGroup:
    """Legacy command-group handle returned by @filter.command_group.

    Sub-command decorators accumulate full-path CommandFilters
    ("group sub") on the target handler.
    """

    def __init__(self, prefix: str, filters: tuple = (), handler: Any = None) -> None:
        self.prefix = prefix
        # Group-scoped filters (RegisteringCommandable.custom_filter in the
        # old core) propagated to every sub-command of the group.
        self.filters = filters
        # The decorator replaces the class attribute with this handle, so the
        # loader must scan the group anchor's filters from here.
        self.handler = handler

    def command(
        self,
        name: str,
        alias: set | None = None,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        full = f"{self.prefix} {name}"
        aliases = {f"{self.prefix} {a}" for a in (alias or set())}

        def decorator(handler: Any) -> Any:
            handler = _accumulate(
                handler,
                CommandFilter(full, aliases, is_sub_command=True, priority=priority),
            )
            for marker in self.filters:
                handler = _accumulate(handler, marker)
            return handler

        return decorator

    def command_group(
        self,
        name: str,
        alias: set | None = None,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        full = f"{self.prefix} {name}"

        def decorator(handler: Any) -> Any:
            handler = _accumulate(
                handler,
                CommandFilter(full, alias, is_group=True, priority=priority),
            )
            for marker in self.filters:
                handler = _accumulate(handler, marker)
            return _CommandGroup(full, self.filters, handler=handler)

        return decorator

    def group(
        self,
        name: str,
        alias: set | None = None,
        **kwargs: Any,
    ) -> Any:
        """Legacy alias of command_group (RegisteringCommandable.group)."""
        return self.command_group(name, alias, **kwargs)

    def custom_filter(
        self,
        custom_filter: Any,
        *args: Any,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        marker = CustomFilter(custom_filter, *args, priority=priority)

        def decorator(awaitable: Any) -> Any:
            if isinstance(awaitable, _CommandGroup):
                return _CommandGroup(
                    awaitable.prefix,
                    (*awaitable.filters, marker),
                    handler=awaitable.handler,
                )
            return _accumulate(awaitable, marker)

        return decorator

    def button_action(
        self,
        action_id: str | None = None,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        """Filter decorator for callback button click interactions."""
        marker = ButtonActionFilter(action_id, priority=priority)

        def decorator(handler: Any) -> Any:
            return _accumulate(handler, marker)

        return decorator

    def ui_action(
        self,
        action_id: str | None = None,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        """Filter decorator for authenticated ChatUI view action interactions."""
        marker = UIActionFilter(action_id, priority=priority)

        def decorator(handler: Any) -> Any:
            return _accumulate(handler, marker)

        return decorator


class HookMarker:
    """Marker accumulated by legacy hook decorators (on_llm_request etc.)."""

    def __init__(self, stage: str, priority: int | None = None) -> None:
        self.stage = stage
        self.priority = priority


class EventMessageType(enum.Flag):
    GROUP_MESSAGE = enum.auto()
    PRIVATE_MESSAGE = enum.auto()
    OTHER_MESSAGE = enum.auto()
    ALL = GROUP_MESSAGE | PRIVATE_MESSAGE | OTHER_MESSAGE


class PermissionType(enum.Flag):
    ADMIN = enum.auto()
    MEMBER = enum.auto()
    GROUP_ADMIN = enum.auto()
    SHARED_GROUP_ADMIN = enum.auto()


class PlatformAdapterType(enum.Flag):
    AIOCQHTTP = enum.auto()
    QQOFFICIAL = enum.auto()
    QQOFFICIAL_WEBHOOK = enum.auto()
    TELEGRAM = enum.auto()
    WECOM = enum.auto()
    WECOM_AI_BOT = enum.auto()
    LARK = enum.auto()
    DINGTALK = enum.auto()
    DISCORD = enum.auto()
    SLACK = enum.auto()
    KOOK = enum.auto()
    VOCECHAT = enum.auto()
    WEIXIN_OFFICIAL_ACCOUNT = enum.auto()
    SATORI = enum.auto()
    MISSKEY = enum.auto()
    LINE = enum.auto()
    MATRIX = enum.auto()
    WEIXIN_OC = enum.auto()
    MATTERMOST = enum.auto()
    WEBCHAT = enum.auto()
    ALL = enum.auto()


# PlatformAdapterType member -> core adapter name, mirroring the old
# ADAPTER_NAME_2_TYPE table (used to build platform constraints).
PLATFORM_ADAPTER_NAMES = {
    PlatformAdapterType.AIOCQHTTP: "aiocqhttp",
    PlatformAdapterType.QQOFFICIAL: "qq_official",
    PlatformAdapterType.QQOFFICIAL_WEBHOOK: "qq_official_webhook",
    PlatformAdapterType.TELEGRAM: "telegram",
    PlatformAdapterType.WECOM: "wecom",
    PlatformAdapterType.WECOM_AI_BOT: "wecom_ai_bot",
    PlatformAdapterType.LARK: "lark",
    PlatformAdapterType.DINGTALK: "dingtalk",
    PlatformAdapterType.DISCORD: "discord",
    PlatformAdapterType.SLACK: "slack",
    PlatformAdapterType.KOOK: "kook",
    PlatformAdapterType.VOCECHAT: "vocechat",
    PlatformAdapterType.WEIXIN_OFFICIAL_ACCOUNT: "weixin_official_account",
    PlatformAdapterType.SATORI: "satori",
    PlatformAdapterType.MISSKEY: "misskey",
    PlatformAdapterType.LINE: "line",
    PlatformAdapterType.MATRIX: "matrix",
    PlatformAdapterType.WEIXIN_OC: "weixin_oc",
    PlatformAdapterType.MATTERMOST: "mattermost",
    PlatformAdapterType.WEBCHAT: "webchat",
}


class PlatformStatus(enum.Enum):
    """Legacy platform runtime status labels."""

    PENDING = "pending"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


class MessageType(enum.Enum):
    """Legacy platform message type."""

    GROUP_MESSAGE = "GroupMessage"
    FRIEND_MESSAGE = "FriendMessage"
    OTHER_MESSAGE = "OtherMessage"


class MessageMember:
    """Legacy message sender record."""

    def __init__(self, user_id: str, nickname: str | None = None) -> None:
        self.user_id = user_id
        self.nickname = nickname

    def __str__(self) -> str:
        return f"User ID: {self.user_id}, Nickname: {self.nickname or 'N/A'}"


class Group:
    """Legacy group record (astrbot.core.platform.astrbot_message.Group)."""

    def __init__(
        self,
        group_id: str = "",
        group_name: str | None = None,
        group_avatar: str | None = None,
        group_owner: str | None = None,
        group_admins: list[str] | None = None,
        members: list[MessageMember] | None = None,
        member_count: int | None = None,
        **_: Any,
    ) -> None:
        self.group_id = group_id
        self.group_name = group_name
        self.group_avatar = group_avatar
        self.group_owner = group_owner
        self.group_admins = group_admins
        self.members = members
        self.member_count = member_count

    def __str__(self) -> str:
        return f"Group ID: {self.group_id}, Name: {self.group_name or 'N/A'}"


class AstrBotMessage:
    """Legacy raw message object (event.message_obj)."""

    def __init__(self, **kwargs: Any) -> None:
        self.type: Any = kwargs.get("type")
        self.self_id: str = kwargs.get("self_id", "")
        self.session_id: str = kwargs.get("session_id", "")
        self.message_id: str = kwargs.get("message_id", "")
        self.group_id: str = kwargs.get("group_id", "")
        self.sender: Any = kwargs.get("sender")
        self.message: list = kwargs.get("message", [])
        self.message_str: str = kwargs.get("message_str", "")
        self.raw_message: Any = kwargs.get("raw_message")
        self.timestamp: Any = kwargs.get("timestamp")


class _FilterNamespace:
    """astrbot.api.event.filter compat namespace."""

    EventMessageType = EventMessageType
    PermissionType = PermissionType
    PermissionTypeFilter = PermissionTypeFilter
    PlatformAdapterType = PlatformAdapterType
    PlatformAdapterTypeFilter = PlatformAdapterTypeFilter
    CustomFilter = CustomFilter
    ButtonActionFilter = ButtonActionFilter
    UIActionFilter = UIActionFilter

    def command(
        self,
        command_name: str,
        alias: set | None = None,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        def decorator(handler: Any) -> Any:
            return _accumulate(
                handler, CommandFilter(command_name, alias, priority=priority)
            )

        return decorator

    def command_group(
        self,
        command_name: str,
        alias: set | None = None,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        def decorator(handler: Any) -> Any:
            _accumulate(
                handler,
                CommandFilter(command_name, alias, is_group=True, priority=priority),
            )
            return _CommandGroup(command_name, handler=handler)

        return decorator

    def regex(self, regex_str: str, priority: int | None = None, **_: Any) -> Any:
        def decorator(handler: Any) -> Any:
            return _accumulate(handler, RegexFilter(regex_str, priority=priority))

        return decorator

    def event_message_type(
        self,
        event_message_type: Any,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        def decorator(handler: Any) -> Any:
            return _accumulate(
                handler,
                EventMessageTypeFilter(event_message_type, priority=priority),
            )

        return decorator

    def on_message(self, *, priority: int | None = None, **_: Any) -> Any:
        """Match any inbound adapter message event."""

        def decorator(handler: Any) -> Any:
            return _accumulate(
                handler,
                EventMessageTypeFilter(EventMessageType.ALL, priority=priority),
            )

        return decorator

    def permission_type(
        self,
        permission_type: Any,
        raise_error: bool = True,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        def decorator(handler: Any) -> Any:
            return _accumulate(
                handler,
                PermissionTypeFilter(permission_type, raise_error, priority=priority),
            )

        return decorator

    def platform_adapter_type(
        self,
        platform_adapter_type_or_str: Any,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        def decorator(handler: Any) -> Any:
            return _accumulate(
                handler,
                PlatformAdapterTypeFilter(
                    platform_adapter_type_or_str, priority=priority
                ),
            )

        return decorator

    def custom_filter(
        self,
        custom_filter: Any,
        *args: Any,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        marker = CustomFilter(custom_filter, *args, priority=priority)

        def decorator(awaitable: Any) -> Any:
            if isinstance(awaitable, _CommandGroup):
                return _CommandGroup(
                    awaitable.prefix,
                    (*awaitable.filters, marker),
                    handler=awaitable.handler,
                )
            return _accumulate(awaitable, marker)

        return decorator

    def button_action(
        self,
        action_id: str | None = None,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        """Filter decorator for callback button click interactions."""
        marker = ButtonActionFilter(action_id, priority=priority)

        def decorator(handler: Any) -> Any:
            return _accumulate(handler, marker)

        return decorator

    def ui_action(
        self,
        action_id: str | None = None,
        priority: int | None = None,
        **_: Any,
    ) -> Any:
        """Filter decorator for authenticated ChatUI view action interactions."""
        marker = UIActionFilter(action_id, priority=priority)

        def decorator(handler: Any) -> Any:
            return _accumulate(handler, marker)

        return decorator

    # ---- Pipeline hooks -----------------------------------------------------

    def _hook(self, stage: str, priority: int | None = None) -> Any:
        def decorator(handler: Any) -> Any:
            return _accumulate(handler, HookMarker(stage, priority=priority))

        return decorator

    def on_llm_request(self, *_args: Any, priority: int | None = None, **_: Any) -> Any:
        return self._hook("llm_request", priority=priority)

    def on_llm_response(
        self, *_args: Any, priority: int | None = None, **_: Any
    ) -> Any:
        return self._hook("llm_response", priority=priority)

    def on_decorating_result(
        self, *_args: Any, priority: int | None = None, **_: Any
    ) -> Any:
        return self._hook("message_result", priority=priority)

    def after_message_sent(
        self, *_args: Any, priority: int | None = None, **_: Any
    ) -> Any:
        return self._hook("message_sent", priority=priority)

    def on_waiting_llm_request(
        self, *_args: Any, priority: int | None = None, **_: Any
    ) -> Any:
        return self._hook("waiting_llm_request", priority=priority)

    def on_using_llm_tool(
        self, *_args: Any, priority: int | None = None, **_: Any
    ) -> Any:
        return self._hook("tool_call", priority=priority)

    def on_llm_tool_respond(
        self, *_args: Any, priority: int | None = None, **_: Any
    ) -> Any:
        return self._hook("tool_result", priority=priority)

    def on_agent_begin(self, *_args: Any, priority: int | None = None, **_: Any) -> Any:
        return self._hook("agent_start", priority=priority)

    def on_agent_done(self, *_args: Any, priority: int | None = None, **_: Any) -> Any:
        return self._hook("agent_end", priority=priority)

    def on_plugin_error(
        self, *_args: Any, priority: int | None = None, **_: Any
    ) -> Any:
        return self._hook("plugin_error", priority=priority)

    def on_plugin_loaded(
        self, *_args: Any, priority: int | None = None, **_: Any
    ) -> Any:
        return self._hook("plugin_loaded", priority=priority)

    def on_plugin_unloaded(
        self, *_args: Any, priority: int | None = None, **_: Any
    ) -> Any:
        return self._hook("plugin_unloaded", priority=priority)

    def on_astrbot_loaded(
        self, *_args: Any, priority: int | None = None, **_: Any
    ) -> Any:
        return self._hook("lifecycle.startup", priority=priority)

    def on_platform_loaded(
        self, *_args: Any, priority: int | None = None, **_: Any
    ) -> Any:
        return self._hook("lifecycle.startup", priority=priority)

    def llm_tool(self, name: str | None = None, **_: Any) -> Any:
        def decorator(handler: Any) -> Any:
            return _accumulate(handler, LLMToolMarker(name or handler.__name__))

        return decorator


class LLMToolMarker:
    """Marker accumulated by the legacy llm_tool decorator."""

    def __init__(self, name: str) -> None:
        self.name = name


filter = _FilterNamespace()


class _CompatSender:
    def __init__(self, event: MessageEvent) -> None:
        self.user_id = event.sender.id
        self.nickname = event.sender.name


class _CompatMessageObj:
    def __init__(self, event: MessageEvent) -> None:
        self.message = [from_sdk_segment(s) for s in event.message]
        self.sender = _CompatSender(event)
        self.message_id = event.message_ref.id
        self.message_str = event.text
        self.type = {
            "private": MessageType.FRIEND_MESSAGE,
            "group": MessageType.GROUP_MESSAGE,
            "other": MessageType.OTHER_MESSAGE,
        }[event.umo.message_type.value]
        self.self_id = ""
        self.session_id = event.umo.session_id
        self.group_id = (
            event.umo.session_id if self.type is MessageType.GROUP_MESSAGE else ""
        )
        self.raw_message = None
        self.timestamp = event.timestamp


class AstrMessageEvent:
    """Facade over the immutable SDK MessageEvent with the old mutable API."""

    def __init__(self, event: MessageEvent, context: Any) -> None:
        self._event = event
        self._context = context
        self._result: MessageEventResult | None = None
        self._stopped = False
        self._extras: dict[str, Any] = {}
        self.message_obj = _CompatMessageObj(event)
        self.message_str = event.text
        self.is_wake = event.is_wake
        self.role = "admin" if event.sender.role is SenderRole.ADMIN else "member"
        self.created_at = event.timestamp.timestamp()
        self.plugins_name = event.extras.get("plugins_name")
        self._call_llm = False
        self._has_send_oper = False
        self._temporary_local_files: list[str] = []

    # ---- identity helpers -------------------------------------------------

    @property
    def unified_msg_origin(self) -> str:
        from ...events import MessageType

        core_type = {
            MessageType.PRIVATE: "FriendMessage",
            MessageType.GROUP: "GroupMessage",
            MessageType.OTHER: "OtherMessage",
        }[self._event.umo.message_type]
        return f"{self._event.umo.platform_id}:{core_type}:{self._event.umo.session_id}"

    @property
    def session(self) -> str:
        return self.unified_msg_origin

    @property
    def session_id(self) -> str:
        return self._event.umo.session_id

    def get_sender_id(self) -> str:
        return self._event.sender.id

    def get_sender_name(self) -> str:
        return self._event.sender.name

    def get_message_str(self) -> str:
        return self._event.text

    def get_messages(self) -> list:
        return self.message_obj.message

    def is_button_interaction(self) -> bool:
        """Return whether this event represents a portable button click."""
        return any(isinstance(c, ButtonInteraction) for c in self.get_messages())

    def get_button_interaction(self) -> ButtonInteraction | None:
        """Return the normalized button click carried by this event, if any."""
        return next(
            (c for c in self.get_messages() if isinstance(c, ButtonInteraction)),
            None,
        )

    def get_ui_interaction(self) -> UIInteraction | None:
        """Return the ChatUI view action attached to this event, if any."""
        return next(
            (c for c in self.get_messages() if isinstance(c, UIInteraction)),
            None,
        )

    def view_result(
        self,
        *,
        data: dict[str, Any],
        name: str | None = None,
        text: str = "",
        title: str = "",
    ) -> Any:
        """Create a named ChatUI view card or update the current interaction card."""
        from .chatui import ViewResult

        if name is None and (self.get_ui_interaction() is None or text):
            raise ValueError("A view update requires a UI interaction and no text.")
        return ViewResult(data=data, name=name, text=text, title=title)

    def is_private_chat(self) -> bool:
        return self._event.is_private

    def is_at_or_wake_command(self) -> bool:
        return self.is_wake

    def get_message_type(self) -> MessageType:
        """Return the legacy platform MessageType enum."""
        from ...events import MessageType as SDKMessageType

        return {
            SDKMessageType.GROUP: MessageType.GROUP_MESSAGE,
            SDKMessageType.PRIVATE: MessageType.FRIEND_MESSAGE,
            SDKMessageType.OTHER: MessageType.OTHER_MESSAGE,
        }[self._event.umo.message_type]

    def get_platform_name(self) -> str:
        """Return the adapter name (e.g. aiocqhttp)."""
        return self._event.platform_type

    def get_platform_id(self) -> str:
        return self._event.umo.platform_id

    def get_session_id(self) -> str:
        return self._event.umo.session_id

    def get_group_id(self) -> str:
        """Return the group id for group messages, else empty."""
        from ...events import MessageType as SDKMessageType

        if self._event.umo.message_type is SDKMessageType.GROUP:
            return self._event.umo.session_id
        return ""

    def get_self_id(self) -> str:
        """Bot self id is Host-side; unavailable across the boundary."""
        return ""

    def get_message_outline(self) -> str:
        """Return a short outline of the message chain."""
        parts = []
        for segment in self._event.message:
            text = getattr(segment, "text", None)
            if text:
                parts.append(text)
            else:
                parts.append(f"[{getattr(segment, 'type', '?')}]")
        return "".join(parts)

    def is_wake_up(self) -> bool:
        return self.is_wake

    def is_admin(self) -> bool:
        return self.role == "admin"

    # ---- result management -------------------------------------------------

    def plain_result(self, text: str) -> MessageEventResult:
        return MessageEventResult().message(text)

    def chain_result(self, chain: MessageChain | list) -> MessageEventResult:
        return MessageEventResult().set_chain(chain)

    def image_result(self, path_or_url: str) -> MessageEventResult:
        result = MessageEventResult()
        result.chain = [Image(file=path_or_url)]
        return result

    def set_result(self, result: MessageEventResult) -> None:
        if isinstance(result, str):
            result = self.plain_result(result)
        self._result = result

    def get_result(self) -> MessageEventResult | None:
        return self._result

    def clear_result(self) -> None:
        self._result = None

    def make_result(self) -> MessageEventResult:
        """Create an empty result, install it, and return it."""
        result = MessageEventResult()
        self._result = result
        return result

    def stop_event(self) -> None:
        self._stopped = True

    def continue_event(self) -> None:
        self._stopped = False

    def is_stopped(self) -> bool:
        return self._stopped

    # ---- event-level flags mirrored to the Host -----------------------------

    @property
    def call_llm(self) -> bool:
        """Whether the default LLM request is suppressed for this event."""
        return self._call_llm

    @call_llm.setter
    def call_llm(self, value: bool) -> None:
        self._call_llm = bool(value)
        # The pipeline reads call_llm on the Host-side event; forward the flag
        # so the change takes effect beyond this local facade.
        try:
            asyncio.get_running_loop().create_task(
                self._context._ctx._invoke_capability(
                    "event.state",
                    "set_call_llm",
                    {"umo": self.unified_msg_origin, "value": self._call_llm},
                ),
            )
        except RuntimeError:
            # No running loop (e.g. sync test contexts): the local flag still
            # mirrors core behavior within this facade.
            pass

    def should_call_llm(self, call_llm: bool) -> None:
        """Suppress the default LLM request for this event (legacy naming)."""
        self.call_llm = call_llm

    # ---- platform adapter facades -------------------------------------------

    @property
    def platform(self) -> Any:
        """Platform adapter facade for this event (snapshot-backed)."""
        manager = getattr(self._context, "platform_manager", None)
        for inst in getattr(manager, "platform_insts", None) or ():
            try:
                if inst.meta().id == self._event.umo.platform_id:
                    return inst
            except Exception:  # a broken entry must not break attribute reads
                continue
        return None

    @property
    def platform_meta(self) -> Any:
        """Platform metadata of the receiving adapter, or None."""
        platform = self.platform
        return platform.meta() if platform is not None else None

    # ---- platform actions forwarded to the in-flight Host event -------------

    async def _call_event_method(self, method: str, **kwargs: Any) -> Any:
        result = await self._context._ctx._invoke_capability(
            "event.state",
            "call_method",
            {"umo": self.unified_msg_origin, "method": method, "args": kwargs},
        )
        if isinstance(result, dict):
            return result.get("result")
        return None

    async def send_typing(self) -> None:
        """Send the typing indicator through the Host event."""
        await self._call_event_method("send_typing")

    async def stop_typing(self) -> None:
        """Stop the typing indicator through the Host event."""
        await self._call_event_method("stop_typing")

    async def react(self, emoji: str) -> None:
        """Add an emoji reaction through the Host event."""
        await self._call_event_method("react", emoji=emoji)

    async def get_group(self, group_id: str | None = None, **kwargs: Any) -> Any:
        """Query group information through the Host event."""
        if group_id is not None:
            kwargs["group_id"] = group_id
        data = await self._call_event_method("get_group", **kwargs)
        if isinstance(data, dict):
            return Group(**data)
        return None

    # ---- event-scoped temporary files (Runner-local) -------------------------

    def track_temporary_local_file(self, path: str) -> None:
        """Register a local file to delete when the event finishes."""
        if path and path not in self._temporary_local_files:
            self._temporary_local_files.append(path)

    def untrack_temporary_local_file(self, path: str) -> None:
        """Exclude a retained attachment from event-scoped cleanup."""
        if path in self._temporary_local_files:
            self._temporary_local_files.remove(path)

    def cleanup_temporary_local_files(self) -> None:
        """Delete every tracked temporary local file."""
        paths = list(self._temporary_local_files)
        self._temporary_local_files.clear()
        for path in paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError as e:
                logger.warning(
                    "Failed to remove temporary local file %s: %s",
                    path,
                    e,
                )

    # ---- extras and proactive send -----------------------------------------

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value

    def get_extra(self, key: str | None = None, default: Any = None) -> Any:
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def clear_extra(self) -> None:
        self._extras.clear()

    async def send(self, message: MessageChain | MessageEventResult | str) -> None:
        """Proactively send a message to this event's session."""
        from ...messages import to_message_chain

        if isinstance(message, MessageEventResult):
            chain = MessageChain(chain=message.chain).to_sdk()
        elif isinstance(message, MessageChain):
            chain = message.to_sdk()
        else:
            chain = to_message_chain(message)
        await self._context._ctx.messages.send(self._event.umo, chain)
        self._has_send_oper = True

    async def process_buffer(self, buffer: str, pattern: re.Pattern) -> str:
        """Split a streaming text buffer by regex and proactively send matches."""
        while True:
            match = re.search(pattern, buffer)
            if not match:
                break
            matched_text = match.group().strip()
            if matched_text:
                await self.send(MessageChain(chain=[Plain(matched_text)]))
                await asyncio.sleep(0)
            buffer = buffer[match.end() :]
        return buffer

    async def send_streaming(
        self,
        generator: Any,
        use_fallback: bool = False,
    ) -> None:
        """Stream incremental MessageChain chunks through the Host event."""
        from ...messages import to_message_chain

        async def _sdk_chunks():
            async for chunk in generator:
                if isinstance(chunk, MessageChain):
                    yield chunk.to_sdk()
                else:
                    yield to_message_chain(chunk)

        await self._context._ctx.events.send_streaming(
            self.unified_msg_origin,
            _sdk_chunks(),
            use_fallback=use_fallback,
        )
        self._has_send_oper = True

    def request_llm(
        self,
        prompt: str,
        func_tool_manager: Any = None,
        tool_set: Any = None,
        session_id: str = "",
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        contexts: list | None = None,
        system_prompt: str = "",
        conversation: Any = None,
    ) -> Any:
        """Build a legacy ProviderRequest to yield as the handler result.

        The compat wrapper executes it via the provider facade and yields the
        completion as a plain result.
        """
        from .provider import ProviderRequest

        if contexts and conversation:
            conversation = None
        return ProviderRequest(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls or [],
            audio_urls=audio_urls or [],
            func_tool=tool_set,
            contexts=contexts or [],
            system_prompt=system_prompt,
            conversation=conversation,
        )


def translate_compat_result(
    item: Any,
    event: AstrMessageEvent,
) -> Any:
    """Translate one yielded legacy value into an SDK EventResult-ish value."""
    from ...results import MessageResult
    from ...results import ViewResult as SDKViewResult
    from .chatui import ViewResult as CompatViewResult

    if item is None:
        return None
    if isinstance(item, CompatViewResult):
        return item.to_sdk_result(
            propagation=Propagation.STOP if event.is_stopped() else Propagation.CONTINUE
        )
    if isinstance(item, SDKViewResult):
        return item
    if isinstance(item, MessageEventResult):
        sdk_result = item.to_sdk_result()
        return sdk_result
    if isinstance(item, MessageChain):
        return MessageResult(
            propagation=(
                Propagation.STOP if event.is_stopped() else Propagation.CONTINUE
            ),
            message=item.to_sdk(),
        )
    if isinstance(item, str):
        return MessageResult(
            propagation=(
                Propagation.STOP if event.is_stopped() else Propagation.CONTINUE
            ),
            message=MessageChain(chain=[Plain(item)]).to_sdk(),
        )
    return item
