"""旧版 ``AstrMessageEvent`` 的兼容包装。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ...events import MessageEvent
from ..message.chain import MessageChain
from ..message.components import BaseMessageComponent
from ..platform.platform_metadata import PlatformMetadata
from .astrbot_message import AstrBotMessage, Group, MessageMember
from .event_result import MessageEventResult
from .message_session import MessageSession
from .message_type import MessageType


def _coerce_message_type(
    message_type: MessageType | str | None,
    *,
    has_group: bool = False,
    has_user: bool = False,
) -> MessageType:
    if isinstance(message_type, MessageType):
        return message_type
    if isinstance(message_type, str):
        try:
            return MessageType(message_type)
        except ValueError:
            pass
    if has_group:
        return MessageType.GROUP_MESSAGE
    if has_user:
        return MessageType.FRIEND_MESSAGE
    return MessageType.OTHER_MESSAGE


class AstrMessageEventModel(BaseModel):
    message_str: str
    message_obj: AstrBotMessage
    platform_meta: PlatformMetadata | None = None
    session_id: str
    role: Literal["admin", "member"] = "member"
    is_wake: bool = False
    is_at_or_wake_command: bool = False
    extras: dict[str, Any] = Field(default_factory=dict)
    result: MessageEventResult | None = None
    has_send_oper: bool = False
    call_llm: bool = False
    plugins_name: list[str] = Field(default_factory=list)

    @classmethod
    def from_event(cls, event: "AstrMessageEvent") -> "AstrMessageEventModel":
        return cls(
            message_str=event.get_message_str(),
            message_obj=event.message_obj,
            platform_meta=event.platform_meta,
            session_id=event.session_id,
            role=event.role,
            is_wake=event.is_wake,
            is_at_or_wake_command=event.is_at_or_wake_command,
            extras=dict(event.get_extra()),
            result=event.get_result(),
            has_send_oper=event.has_send_oper,
            call_llm=event.call_llm,
            plugins_name=list(event._plugins_name),
        )

    def to_event(self) -> "AstrMessageEvent":
        return AstrMessageEvent(
            text=self.message_str,
            user_id=self.message_obj.sender.user_id,
            group_id=self.message_obj.group_id,
            platform=self.platform_meta.id if self.platform_meta else None,
            session_id=self.session_id,
            raw=self.message_obj.raw_message,
            message_obj=self.message_obj,
            platform_meta=self.platform_meta,
            role=self.role,
            is_wake=self.is_wake,
            is_at_or_wake_command=self.is_at_or_wake_command,
            extras=self.extras,
            result=self.result,
            has_send_oper=self.has_send_oper,
            call_llm=self.call_llm,
            plugins_name=self.plugins_name,
        )


class AstrMessageEvent(MessageEvent):
    def __init__(
        self,
        *,
        text: str = "",
        user_id: str | None = None,
        group_id: str | None = None,
        platform: str | None = None,
        session_id: str | None = None,
        raw: dict[str, Any] | None = None,
        context=None,
        reply_handler=None,
        message_obj: AstrBotMessage | None = None,
        platform_meta: PlatformMetadata | None = None,
        role: Literal["admin", "member"] = "member",
        is_wake: bool = False,
        is_at_or_wake_command: bool = False,
        extras: dict[str, Any] | None = None,
        result: MessageEventResult | None = None,
        has_send_oper: bool = False,
        call_llm: bool = False,
        plugins_name: list[str] | None = None,
    ) -> None:
        super().__init__(
            text=text,
            user_id=user_id,
            group_id=group_id,
            platform=platform,
            session_id=session_id,
            raw=raw,
            context=context,
            reply_handler=reply_handler,
        )
        self.message_obj = message_obj or self._build_message_obj()
        self.platform_meta = platform_meta
        self.role = role
        self.is_wake = is_wake
        self.is_at_or_wake_command = is_at_or_wake_command
        self._extras = dict(extras or {})
        self._result = result
        self.has_send_oper = has_send_oper
        self.call_llm = call_llm
        self._plugins_name = list(plugins_name or [])
        self.session = MessageSession(
            platform_name=self.get_platform_id(),
            message_type=self.get_message_type(),
            session_id=self.session_id,
        )
        self.unified_msg_origin = str(self.session)
        self.platform = self.platform_meta or self.platform

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        context=None,
        reply_handler=None,
    ) -> "AstrMessageEvent":
        return cls(
            text=str(payload.get("text", payload.get("message_str", ""))),
            user_id=payload.get("user_id"),
            group_id=payload.get("group_id"),
            platform=payload.get("platform"),
            session_id=payload.get("session_id"),
            raw=payload,
            context=context,
            reply_handler=reply_handler,
        )

    @classmethod
    def from_message_event(cls, event: MessageEvent) -> "AstrMessageEvent":
        if isinstance(event, cls):
            return event
        return cls(
            text=event.text,
            user_id=event.user_id,
            group_id=event.group_id,
            platform=event.platform,
            session_id=event.session_id,
            raw=event.raw,
            context=getattr(event, "_context", None),
            reply_handler=getattr(event, "_reply_handler", None),
        )

    def _build_message_obj(self) -> AstrBotMessage:
        sender_payload = (
            self.raw.get("sender") if isinstance(self.raw, dict) else {}
        ) or {}
        sender = MessageMember(
            user_id=str(sender_payload.get("user_id") or self.user_id or ""),
            nickname=sender_payload.get("nickname"),
        )
        group = None
        group_payload = (
            self.raw.get("group") if isinstance(self.raw, dict) else None
        ) or None
        if isinstance(group_payload, dict):
            group = Group(
                group_id=str(group_payload.get("group_id") or self.group_id or ""),
                group_name=group_payload.get("group_name"),
                group_avatar=group_payload.get("group_avatar"),
                group_owner=group_payload.get("group_owner"),
                group_admins=group_payload.get("group_admins"),
                members=group_payload.get("members"),
            )
        elif self.group_id:
            group = Group(group_id=self.group_id)

        message_components = self.raw.get("message")
        if not isinstance(message_components, list):
            message_components = []

        message_type = _coerce_message_type(
            self.raw.get("message_type"),
            has_group=bool(group),
            has_user=bool(self.user_id),
        )
        return AstrBotMessage(
            type=message_type,
            self_id=str(self.raw.get("self_id", "")),
            session_id=self.session_id,
            message_id=str(self.raw.get("message_id", "")),
            sender=sender,
            message=message_components,
            message_str=self.text,
            raw_message=self.raw,
            group=group,
        )

    def get_platform_name(self) -> str:
        if self.platform_meta is not None:
            return self.platform_meta.name
        return str(self.raw.get("platform_name") or self.raw.get("platform") or "")

    def get_platform_id(self) -> str:
        if self.platform_meta is not None:
            return self.platform_meta.id
        return str(self.raw.get("platform_id") or self.raw.get("platform") or "")

    def get_message_str(self) -> str:
        return self.text

    def get_messages(self) -> list[BaseMessageComponent]:
        return list(self.message_obj.message)

    def get_message_type(self) -> MessageType:
        return self.message_obj.type

    def get_session_id(self) -> str:
        return self.session_id

    def get_group_id(self) -> str:
        return self.message_obj.group_id

    def get_self_id(self) -> str:
        return self.message_obj.self_id

    def get_sender_id(self) -> str:
        return self.message_obj.sender.user_id

    def get_sender_name(self) -> str | None:
        return self.message_obj.sender.nickname

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value

    def get_extra(self, key: str | None = None, default: Any = None) -> Any:
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def clear_extra(self) -> None:
        self._extras.clear()

    def is_private_chat(self) -> bool:
        return self.get_message_type() == MessageType.FRIEND_MESSAGE

    def is_wake_up(self) -> bool:
        return self.is_wake

    def is_admin(self) -> bool:
        return self.role == "admin"

    def set_result(self, result: MessageEventResult | str) -> None:
        if isinstance(result, str):
            result = MessageEventResult().message(result)
        self._result = result

    def stop_event(self) -> None:
        if self._result is None:
            self._result = MessageEventResult().stop_event()
            return
        self._result.stop_event()

    def continue_event(self) -> None:
        if self._result is None:
            self._result = MessageEventResult().continue_event()
            return
        self._result.continue_event()

    def is_stopped(self) -> bool:
        if self._result is None:
            return False
        return self._result.is_stopped()

    def should_call_llm(self, call_llm: bool) -> None:
        self.call_llm = call_llm

    def get_result(self) -> MessageEventResult | None:
        return self._result

    def clear_result(self) -> None:
        self._result = None

    def make_result(self) -> MessageEventResult:
        return MessageEventResult()

    def plain_result(self, text: str) -> MessageEventResult:
        return MessageEventResult().message(text)

    def image_result(self, url_or_path: str) -> MessageEventResult:
        result = MessageEventResult()
        if url_or_path.startswith("http"):
            return result.url_image(url_or_path)
        return result.file_image(url_or_path)

    def chain_result(self, chain: list[BaseMessageComponent]) -> MessageEventResult:
        result = MessageEventResult()
        result.chain = chain
        return result

    async def send(self, message: MessageChain) -> None:
        self.has_send_oper = True
        runtime_context = getattr(self, "_context", None)
        if runtime_context is not None and not message.is_plain_text_only():
            await runtime_context.platform.send_chain(
                self.session_id,
                message.to_payload(),
            )
            return
        await self.reply(message.get_plain_text())

    async def react(self, emoji: str) -> None:
        self.has_send_oper = True
        await self.reply(emoji)

    async def get_group(self, group_id: str | None = None, **kwargs) -> Group | None:
        if self.message_obj.group is None:
            return None
        if group_id is None or self.message_obj.group.group_id == group_id:
            return self.message_obj.group
        return None
