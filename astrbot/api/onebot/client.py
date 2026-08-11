"""Typing surface for the event-bound OneBot client facade."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .actions import (
    OneBotActionResult,
    OneBotFileResult,
    OneBotGroupInfo,
    OneBotHistoryPage,
    OneBotMemberInfo,
    OneBotMessageReceipt,
)
from .events import OneBotEvent


class OneBotMessages(Protocol):
    async def send(
        self,
        *,
        message: object,
        user_id: str | int | None = None,
        group_id: str | int | None = None,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> OneBotMessageReceipt: ...

    async def send_private(
        self,
        *,
        user_id: str | int,
        message: object,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> OneBotMessageReceipt: ...

    async def send_group(
        self,
        *,
        group_id: str | int,
        message: object,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> OneBotMessageReceipt: ...

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
    ) -> OneBotMessageReceipt: ...

    async def delete(self, *, message_id: str | int) -> OneBotActionResult: ...

    async def get(self, *, message_id: str | int) -> OneBotActionResult: ...

    async def get_forward(self, *, forward_id: str | int) -> OneBotActionResult: ...


class OneBotDirectory(Protocol):
    async def login_info(self) -> OneBotActionResult: ...

    async def status(self) -> OneBotActionResult: ...

    async def version_info(self) -> OneBotActionResult: ...

    async def group_info(self, *, group_id: str | int) -> OneBotGroupInfo: ...

    async def group_member_info(
        self, *, group_id: str | int, user_id: str | int, no_cache: bool = False
    ) -> OneBotMemberInfo: ...

    async def group_member_list(
        self, *, group_id: str | int, no_cache: bool | None = None
    ) -> tuple[OneBotMemberInfo, ...]: ...

    async def stranger_info(
        self, *, user_id: str | int, no_cache: bool = False
    ) -> OneBotMemberInfo: ...

    async def image(
        self, *, file: str | None = None, file_id: str | None = None
    ) -> OneBotFileResult: ...

    async def file(
        self, *, file: str | None = None, file_id: str | None = None
    ) -> OneBotFileResult: ...

    async def group_file_url(
        self, *, group_id: str | int, file_id: str
    ) -> OneBotFileResult: ...

    async def private_file_url(self, *, file_id: str) -> OneBotFileResult: ...


class OneBotGroups(Protocol):
    async def set_admin(
        self, *, group_id: str | int, user_id: str | int, enable: bool = True
    ) -> OneBotActionResult: ...

    async def ban(
        self, *, group_id: str | int, user_id: str | int, duration: int | float = 0
    ) -> OneBotActionResult: ...

    async def set_card(
        self, *, group_id: str | int, user_id: str | int, card: str | None = None
    ) -> OneBotActionResult: ...

    async def kick(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        reject_add_request: bool | None = None,
    ) -> OneBotActionResult: ...

    async def kick_many(
        self,
        *,
        group_id: str | int,
        user_ids: list[str | int],
        reject_add_request: bool | None = None,
    ) -> OneBotActionResult: ...

    async def leave(
        self, *, group_id: str | int, is_dismiss: bool | None = None
    ) -> OneBotActionResult: ...

    async def whole_ban(
        self, *, group_id: str | int, enable: bool = True
    ) -> OneBotActionResult: ...

    async def set_essence(self, *, message_id: str | int) -> OneBotActionResult: ...

    async def delete_essence(
        self,
        *,
        message_id: str | int | None = None,
        msg_seq: str | None = None,
        msg_random: str | None = None,
        group_id: str | int | None = None,
    ) -> OneBotActionResult: ...


class OneBotRequests(Protocol):
    async def friend(
        self, *, flag: str, approve: bool = True, remark: str | None = None
    ) -> OneBotActionResult: ...

    async def group(
        self,
        *,
        flag: str,
        sub_type: str,
        approve: bool = True,
        reason: str | None = None,
    ) -> OneBotActionResult: ...


class OneBotHistory(Protocol):
    async def group(
        self,
        *,
        group_id: str | int,
        count: int = 20,
        message_seq: str | int | None = None,
    ) -> OneBotHistoryPage: ...

    async def friend(
        self,
        *,
        user_id: str | int,
        count: int = 20,
        message_seq: str | int | None = None,
    ) -> OneBotHistoryPage: ...


class NapCatQQ(Protocol):
    async def send_like(
        self, *, user_id: str | int, times: int | float = 1
    ) -> OneBotActionResult: ...

    async def friend_poke(
        self, *, user_id: str | int, target_id: str | int | None = None
    ) -> OneBotActionResult: ...

    async def group_poke(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        target_id: str | int | None = None,
    ) -> OneBotActionResult: ...

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
    ) -> OneBotActionResult: ...

    async def set_input_status(
        self, *, user_id: str | int, event_type: int | float = 1
    ) -> OneBotActionResult: ...

    async def get_online_file_messages(
        self, *, user_id: str | int
    ) -> OneBotActionResult: ...

    async def create_flash_task(
        self,
        *,
        files: list[str] | str,
        name: str | None = None,
        thumb_path: str | None = None,
    ) -> OneBotActionResult: ...

    async def get_flash_file_list(self, *, fileset_id: str) -> OneBotActionResult: ...

    async def get_flash_file_url(
        self,
        *,
        fileset_id: str,
        file_name: str | None = None,
        file_index: int | float | None = None,
    ) -> OneBotActionResult: ...

    async def receive_online_file(
        self, *, user_id: str | int, msg_id: str, element_id: str
    ) -> OneBotActionResult: ...

    async def refuse_online_file(
        self, *, user_id: str | int, msg_id: str, element_id: str
    ) -> OneBotActionResult: ...

    async def cancel_online_file(
        self, *, user_id: str | int, msg_id: str
    ) -> OneBotActionResult: ...

    async def send_online_file(
        self, *, user_id: str | int, file_path: str, file_name: str | None = None
    ) -> OneBotActionResult: ...

    async def send_online_folder(
        self,
        *,
        user_id: str | int,
        folder_path: str,
        folder_name: str | None = None,
    ) -> OneBotActionResult: ...

    async def send_flash_message(
        self,
        *,
        fileset_id: str,
        user_id: str | int | None = None,
        group_id: str | int | None = None,
    ) -> OneBotActionResult: ...

    async def fetch_custom_face(self, *, count: int = 48) -> OneBotActionResult: ...

    async def ai_characters(
        self, *, group_id: str | int, chat_type: int | float = 1
    ) -> OneBotActionResult: ...

    async def group_ai_record(
        self,
        *,
        group_id: str | int,
        character: str,
        text: str,
        chat_type: int | float = 1,
        timeout_seconds: float = 10.0,
    ) -> OneBotActionResult: ...


@runtime_checkable
class OneBotClient(Protocol):
    """Runtime facade returned by ``PluginContext.onebot.for_event``."""

    event: OneBotEvent
    messages: OneBotMessages
    directory: OneBotDirectory
    groups: OneBotGroups
    requests: OneBotRequests
    history: OneBotHistory
    qq: NapCatQQ


__all__ = [
    "OneBotClient",
    "OneBotMessages",
    "OneBotDirectory",
    "OneBotGroups",
    "OneBotRequests",
    "OneBotHistory",
    "NapCatQQ",
]
