"""Runtime-owned OneBot capability facade.

This module is deliberately independent from concrete NapCat adapters.  It
only talks to the narrow capability invocation port on ``CoreExecutionContext``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.contracts.onebot import (
    ONEBOT_CAPABILITIES,
    OneBotActionResult,
    OneBotActionValidationError,
    OneBotEvent,
    OneBotFileResult,
    OneBotGroupInfo,
    OneBotHistoryPage,
    OneBotMemberInfo,
    OneBotMessageEvent,
    OneBotMessageReceipt,
)


def _event_payload(event: AstrMessageEvent) -> Mapping[str, Any] | None:
    raw = event.get_extra("onebot_raw_payload")
    if isinstance(raw, Mapping):
        return raw
    raw = event.get_extra("napcat_raw_payload")
    if isinstance(raw, Mapping):
        return raw
    raw = event.get_extra("napcat_event")
    return raw if isinstance(raw, Mapping) else None


class _ActionGroup:
    __slots__ = ("_client", "_capability")

    def __init__(self, client: Any, capability: str) -> None:
        self._client = client
        self._capability = capability

    async def _invoke(self, action: str, **kwargs: Any) -> Any:
        return await self._client._invoke(self._capability, action, **kwargs)


class OneBotMessages(_ActionGroup):
    async def send(
        self,
        *,
        message: Any,
        user_id: str | int | None = None,
        group_id: str | int | None = None,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> OneBotMessageReceipt:
        if user_id is not None and group_id is not None:
            raise OneBotActionValidationError(
                "user_id and group_id are mutually exclusive", action="send"
            )
        if group_id is not None:
            return await self._invoke(
                "send_group",
                group_id=group_id,
                message=message,
                auto_escape=auto_escape,
                timeout_ms=timeout_ms,
            )
        if user_id is not None:
            return await self._invoke(
                "send_private",
                user_id=user_id,
                message=message,
                auto_escape=auto_escape,
                timeout_ms=timeout_ms,
            )
        return await self._invoke(
            "send",
            message=message,
            auto_escape=auto_escape,
            timeout_ms=timeout_ms,
        )

    async def send_private(
        self,
        *,
        user_id: str | int,
        message: Any,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> OneBotMessageReceipt:
        return await self._invoke(
            "send_private",
            user_id=user_id,
            message=message,
            auto_escape=auto_escape,
            timeout_ms=timeout_ms,
        )

    async def send_group(
        self,
        *,
        group_id: str | int,
        message: Any,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> OneBotMessageReceipt:
        return await self._invoke(
            "send_group",
            group_id=group_id,
            message=message,
            auto_escape=auto_escape,
            timeout_ms=timeout_ms,
        )

    async def send_forward(
        self,
        *,
        messages: list[object],
        user_id: str | int | None = None,
        group_id: str | int | None = None,
        source: str | None = None,
        summary: str | None = None,
        prompt: str | None = None,
        news: list[object] | None = None,
        timeout_ms: float | None = None,
    ) -> OneBotMessageReceipt:
        if (user_id is None) == (group_id is None):
            raise OneBotActionValidationError(
                "Exactly one of user_id or group_id is required", action="send_forward"
            )
        target = {"user_id": user_id} if user_id is not None else {"group_id": group_id}
        return await self._invoke(
            "send_forward",
            messages=messages,
            source=source,
            summary=summary,
            prompt=prompt,
            news=news,
            timeout_ms=timeout_ms,
            **target,
        )

    async def delete(self, *, message_id: str | int) -> OneBotActionResult:
        return await self._invoke("delete", message_id=message_id)

    async def get(self, *, message_id: str | int) -> OneBotActionResult:
        return await self._invoke("get_message", message_id=message_id)

    async def get_forward(self, *, forward_id: str | int) -> OneBotActionResult:
        return await self._invoke("get_forward_message", forward_id=forward_id)


class OneBotDirectory(_ActionGroup):
    async def login_info(self) -> OneBotActionResult:
        return await self._invoke("get_login_info")

    async def status(self) -> OneBotActionResult:
        return await self._invoke("get_status")

    async def version_info(self) -> OneBotActionResult:
        return await self._invoke("get_version_info")

    async def group_info(self, *, group_id: str | int) -> OneBotGroupInfo:
        return await self._invoke("get_group_info", group_id=group_id)

    async def group_member_info(
        self, *, group_id: str | int, user_id: str | int, no_cache: bool = False
    ) -> OneBotMemberInfo:
        return await self._invoke(
            "get_group_member_info",
            group_id=group_id,
            user_id=user_id,
            no_cache=no_cache,
        )

    async def group_member_list(
        self, *, group_id: str | int, no_cache: bool | None = None
    ) -> tuple[OneBotMemberInfo, ...]:
        return await self._invoke(
            "get_group_member_list", group_id=group_id, no_cache=no_cache
        )

    async def stranger_info(
        self, *, user_id: str | int, no_cache: bool = False
    ) -> OneBotMemberInfo:
        return await self._invoke(
            "get_stranger_info", user_id=user_id, no_cache=no_cache
        )

    async def image(
        self, *, file: str | None = None, file_id: str | None = None
    ) -> OneBotFileResult:
        return await self._invoke("get_image", file=file, file_id=file_id)

    async def file(
        self, *, file: str | None = None, file_id: str | None = None
    ) -> OneBotFileResult:
        return await self._invoke("get_file", file=file, file_id=file_id)

    async def group_file_url(
        self, *, group_id: str | int, file_id: str
    ) -> OneBotFileResult:
        return await self._invoke(
            "get_group_file_url", group_id=group_id, file_id=file_id
        )

    async def private_file_url(self, *, file_id: str) -> OneBotFileResult:
        return await self._invoke("get_private_file_url", file_id=file_id)

    get_login_info = login_info
    get_status = status
    get_version_info = version_info
    get_group_info = group_info
    get_group_member_info = group_member_info
    get_group_member_list = group_member_list
    get_stranger_info = stranger_info
    get_image = image
    get_file = file
    get_group_file_url = group_file_url
    get_private_file_url = private_file_url


class OneBotGroups(_ActionGroup):
    async def set_admin(
        self, *, group_id: str | int, user_id: str | int, enable: bool = True
    ) -> OneBotActionResult:
        return await self._invoke(
            "set_group_admin", group_id=group_id, user_id=user_id, enable=enable
        )

    async def ban(
        self, *, group_id: str | int, user_id: str | int, duration: int | float = 0
    ) -> OneBotActionResult:
        return await self._invoke(
            "set_group_ban", group_id=group_id, user_id=user_id, duration=duration
        )

    async def set_card(
        self, *, group_id: str | int, user_id: str | int, card: str | None = None
    ) -> OneBotActionResult:
        return await self._invoke(
            "set_group_card", group_id=group_id, user_id=user_id, card=card
        )

    async def kick(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        reject_add_request: bool | None = None,
    ) -> OneBotActionResult:
        return await self._invoke(
            "kick_group_member",
            group_id=group_id,
            user_id=user_id,
            reject_add_request=reject_add_request,
        )

    async def kick_many(
        self,
        *,
        group_id: str | int,
        user_ids: list[str | int],
        reject_add_request: bool | None = None,
    ) -> OneBotActionResult:
        return await self._invoke(
            "kick_group_members",
            group_id=group_id,
            user_ids=user_ids,
            reject_add_request=reject_add_request,
        )

    async def leave(
        self, *, group_id: str | int, is_dismiss: bool | None = None
    ) -> OneBotActionResult:
        return await self._invoke(
            "leave_group", group_id=group_id, is_dismiss=is_dismiss
        )

    async def whole_ban(
        self, *, group_id: str | int, enable: bool = True
    ) -> OneBotActionResult:
        return await self._invoke(
            "set_group_whole_ban", group_id=group_id, enable=enable
        )

    async def set_essence(self, *, message_id: str | int) -> OneBotActionResult:
        return await self._invoke("set_essence_message", message_id=message_id)

    async def delete_essence(
        self,
        *,
        message_id: str | int | None = None,
        msg_seq: str | None = None,
        msg_random: str | None = None,
        group_id: str | int | None = None,
    ) -> OneBotActionResult:
        if message_id is None and (msg_seq is None or msg_random is None):
            raise OneBotActionValidationError(
                "message_id or both msg_seq and msg_random are required",
                action="delete_essence_message",
            )
        return await self._invoke(
            "delete_essence_message",
            message_id=message_id,
            msg_seq=msg_seq,
            msg_random=msg_random,
            group_id=group_id,
        )

    set_group_admin = set_admin
    set_group_ban = ban
    set_group_card = set_card
    kick_group_member = kick
    kick_group_members = kick_many
    leave_group = leave
    set_group_whole_ban = whole_ban
    set_essence_message = set_essence
    delete_essence_message = delete_essence


class OneBotRequests(_ActionGroup):
    async def friend(
        self, *, flag: str, approve: bool = True, remark: str | None = None
    ) -> OneBotActionResult:
        return await self._invoke(
            "set_friend_add_request", flag=flag, approve=approve, remark=remark
        )

    async def group(
        self,
        *,
        flag: str,
        sub_type: str,
        approve: bool = True,
        reason: str | None = None,
    ) -> OneBotActionResult:
        return await self._invoke(
            "set_group_add_request",
            flag=flag,
            sub_type=sub_type,
            approve=approve,
            reason=reason,
        )

    set_friend_add_request = friend
    set_group_add_request = group


class OneBotHistory(_ActionGroup):
    async def group(
        self,
        *,
        group_id: str | int,
        count: int = 20,
        message_seq: str | int | None = None,
    ) -> OneBotHistoryPage:
        return await self._invoke(
            "get_group_msg_history",
            group_id=group_id,
            count=count,
            message_seq=message_seq,
        )

    async def friend(
        self,
        *,
        user_id: str | int,
        count: int = 20,
        message_seq: str | int | None = None,
    ) -> OneBotHistoryPage:
        return await self._invoke(
            "get_friend_msg_history",
            user_id=user_id,
            count=count,
            message_seq=message_seq,
        )

    get_group_msg_history = group
    get_friend_msg_history = friend


class NapCatQQ(_ActionGroup):
    async def send_like(
        self, *, user_id: str | int, times: int | float = 1
    ) -> OneBotActionResult:
        return await self._invoke("send_like", user_id=user_id, times=times)

    async def friend_poke(
        self, *, user_id: str | int, target_id: str | int | None = None
    ) -> OneBotActionResult:
        return await self._invoke("friend_poke", user_id=user_id, target_id=target_id)

    async def group_poke(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        target_id: str | int | None = None,
    ) -> OneBotActionResult:
        return await self._invoke(
            "group_poke", group_id=group_id, user_id=user_id, target_id=target_id
        )

    async def group_notice(
        self,
        *,
        group_id: str | int,
        content: str,
        pinned: int | float | None = None,
        type_: int | float | None = None,
        confirm_required: int | float | None = None,
        is_show_edit_card: int | float | None = None,
        tip_window_type: int | float | None = None,
        image: str | None = None,
    ) -> OneBotActionResult:
        return await self._invoke(
            "send_group_notice",
            group_id=group_id,
            content=content,
            pinned=pinned,
            type_=type_,
            confirm_required=confirm_required,
            is_show_edit_card=is_show_edit_card,
            tip_window_type=tip_window_type,
            image=image,
        )

    async def set_input_status(
        self, *, user_id: str | int, event_type: int | float = 1
    ) -> OneBotActionResult:
        return await self._invoke(
            "set_input_status", user_id=user_id, event_type=event_type
        )

    async def get_online_file_messages(
        self, *, user_id: str | int
    ) -> OneBotActionResult:
        return await self._invoke("get_online_file_messages", user_id=user_id)

    async def create_flash_task(
        self,
        *,
        files: list[str] | str,
        name: str | None = None,
        thumb_path: str | None = None,
    ) -> OneBotActionResult:
        return await self._invoke(
            "create_flash_task", files=files, name=name, thumb_path=thumb_path
        )

    async def get_flash_file_list(self, *, fileset_id: str) -> OneBotActionResult:
        return await self._invoke("get_flash_file_list", fileset_id=fileset_id)

    async def get_flash_file_url(
        self,
        *,
        fileset_id: str,
        file_name: str | None = None,
        file_index: int | float | None = None,
    ) -> OneBotActionResult:
        return await self._invoke(
            "get_flash_file_url",
            fileset_id=fileset_id,
            file_name=file_name,
            file_index=file_index,
        )

    async def receive_online_file(
        self, *, user_id: str | int, msg_id: str, element_id: str
    ) -> OneBotActionResult:
        return await self._invoke(
            "receive_online_file", user_id=user_id, msg_id=msg_id, element_id=element_id
        )

    async def refuse_online_file(
        self, *, user_id: str | int, msg_id: str, element_id: str
    ) -> OneBotActionResult:
        return await self._invoke(
            "refuse_online_file", user_id=user_id, msg_id=msg_id, element_id=element_id
        )

    async def cancel_online_file(
        self, *, user_id: str | int, msg_id: str
    ) -> OneBotActionResult:
        return await self._invoke("cancel_online_file", user_id=user_id, msg_id=msg_id)

    async def send_online_file(
        self, *, user_id: str | int, file_path: str, file_name: str | None = None
    ) -> OneBotActionResult:
        return await self._invoke(
            "send_online_file",
            user_id=user_id,
            file_path=file_path,
            file_name=file_name,
        )

    async def send_online_folder(
        self, *, user_id: str | int, folder_path: str, folder_name: str | None = None
    ) -> OneBotActionResult:
        return await self._invoke(
            "send_online_folder",
            user_id=user_id,
            folder_path=folder_path,
            folder_name=folder_name,
        )

    async def send_flash_message(
        self,
        *,
        fileset_id: str,
        user_id: str | int | None = None,
        group_id: str | int | None = None,
    ) -> OneBotActionResult:
        return await self._invoke(
            "send_flash_message",
            fileset_id=fileset_id,
            user_id=user_id,
            group_id=group_id,
        )

    async def fetch_custom_face(self, *, count: int = 48) -> OneBotActionResult:
        return await self._invoke("fetch_custom_face", count=count)

    async def ai_characters(
        self, *, group_id: str | int, chat_type: int | float = 1
    ) -> OneBotActionResult:
        return await self._invoke(
            "get_ai_characters", group_id=group_id, chat_type=chat_type
        )

    async def group_ai_record(
        self,
        *,
        group_id: str | int,
        character: str,
        text: str,
        chat_type: int | float = 1,
        timeout_seconds: float = 10.0,
    ) -> OneBotActionResult:
        return await self._invoke(
            "send_group_ai_record",
            group_id=group_id,
            character=character,
            text=text,
            chat_type=chat_type,
            timeout_seconds=timeout_seconds,
        )

    send_group_notice = group_notice
    send_group_ai_record = group_ai_record
    get_ai_characters = ai_characters


class OneBotClient:
    """An event-bound, typed facade; never the underlying websocket client."""

    __slots__ = (
        "_execution",
        "_platform_id",
        "event",
        "messages",
        "directory",
        "groups",
        "requests",
        "history",
        "qq",
    )

    def __init__(self, execution: Any, platform_id: str, event: OneBotEvent) -> None:
        self._execution = execution
        self._platform_id = platform_id
        self.event = event
        self.messages = OneBotMessages(self, "onebot.v11")
        self.directory = OneBotDirectory(self, "onebot.v11")
        self.groups = OneBotGroups(self, "onebot.v11")
        self.requests = OneBotRequests(self, "onebot.v11")
        self.history = OneBotHistory(self, "onebot.v11")
        self.qq = NapCatQQ(self, "napcat.qq")

    async def _invoke(self, capability: str, action: str, **kwargs: Any) -> Any:
        if action == "send" and "user_id" not in kwargs and "group_id" not in kwargs:
            if isinstance(self.event, OneBotMessageEvent):
                if self.event.group_id is not None:
                    kwargs["group_id"] = self.event.group_id
                elif self.event.user_id is not None:
                    kwargs["user_id"] = self.event.user_id
        return await self._execution.invoke_platform_capability(
            self._platform_id, capability, action, **kwargs
        )


class OneBotCapability:
    """Expose OneBot only when an event carries an adapter-provided payload."""

    __slots__ = ("_execution",)

    def __init__(self, execution: Any) -> None:
        self._execution = execution

    def event(self, event: AstrMessageEvent) -> OneBotEvent | None:
        payload = _event_payload(event)
        if payload is None or not payload.get("post_type"):
            return None
        return OneBotEvent.from_payload(payload)

    def for_event(self, event: AstrMessageEvent) -> OneBotClient | None:
        onebot_event = self.event(event)
        if onebot_event is None:
            return None
        return OneBotClient(self._execution, event.get_platform_id(), onebot_event)

    def supports(
        self, event: AstrMessageEvent, capability: str, action: str | None = None
    ) -> bool:
        if self.event(event) is None:
            return False
        if capability == "napcat.qq" and event.get_extra("platform_event") != "napcat":
            return False
        descriptor = next(
            (item for item in ONEBOT_CAPABILITIES if item.name == capability), None
        )
        if descriptor is None:
            return False
        if action is not None and descriptor.action(action) is None:
            return False
        get_capabilities = getattr(self._execution, "get_platform_capabilities", None)
        if callable(get_capabilities):
            try:
                declared = get_capabilities(event.get_platform_id())
            except Exception:
                return False
            if isinstance(declared, (tuple, list)):
                platform_capability = next(
                    (item for item in declared if item.name == capability), None
                )
                if platform_capability is None:
                    return False
                return action is None or platform_capability.action(action) is not None
        return True


__all__ = ["OneBotCapability", "OneBotClient"]
