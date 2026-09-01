from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.message.components import Forward, OnlineFile
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import Group, MessageMember
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.send_result import PlatformSendResult

if TYPE_CHECKING:
    from .napcat_platform_adapter import NapCatPlatformAdapter


class NapCatMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj,
        platform_meta,
        session_id: str,
        adapter: NapCatPlatformAdapter,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._adapter = adapter

    async def send(self, message: MessageChain) -> PlatformSendResult | None:
        if not message.chain:
            return await super().send(message)
        await self._adapter.send_by_route(self.route_identity, message)
        return await super().send(message)

    async def delete(self) -> None:
        if self.get_extra("onebot_post_type") != "message":
            raise ValueError("delete() is only available for NapCat message events")

        message_id = getattr(self.message_obj, "message_id", "")
        if not message_id:
            raise ValueError("current NapCat event does not contain a message_id")
        await self._adapter.client.delete_message(message_id)

    def is_notice_type(self, notice_type: str, *, sub_type: str | None = None) -> bool:
        if self.get_extra("onebot_post_type") != "notice":
            return False
        if self.get_extra("onebot_notice_type") != notice_type:
            return False
        if sub_type is not None and self.get_extra("onebot_sub_type") != sub_type:
            return False
        return True

    def get_recall_info(self) -> dict[str, object] | None:
        notice_type = self.get_extra("onebot_notice_type")
        if notice_type not in {"friend_recall", "group_recall"}:
            return None

        info: dict[str, object] = {
            "notice_type": notice_type,
            "message_id": self.get_extra("napcat_message_id"),
            "user_id": self.get_extra("napcat_user_id"),
        }
        group_id = self.get_extra("napcat_group_id")
        operator_id = self.get_extra("napcat_operator_id")
        if group_id is not None:
            info["group_id"] = group_id
        if operator_id is not None:
            info["operator_id"] = operator_id
        return info

    def get_upload_info(self) -> dict[str, object] | None:
        if not self.is_notice_type("group_upload"):
            return None

        raw_event = getattr(self.message_obj, "raw_message", None)
        file_info = getattr(raw_event, "file", None)
        payload = {
            "notice_type": "group_upload",
            "group_id": self.get_extra("napcat_group_id"),
            "user_id": self.get_extra("napcat_user_id"),
            "file": self._attrs_or_mapping_to_dict(file_info),
        }
        return payload

    def get_reaction_info(self) -> dict[str, object] | None:
        notice_type = self.get_extra("onebot_notice_type")
        raw_event = getattr(self.message_obj, "raw_message", None)

        if notice_type == "group_msg_emoji_like":
            likes = getattr(raw_event, "likes", None)
            serialized_likes: list[object] = []
            if isinstance(likes, list):
                serialized_likes = [
                    self._attrs_or_mapping_to_dict(item) for item in likes
                ]
            info: dict[str, object] = {
                "notice_type": notice_type,
                "group_id": self.get_extra("napcat_group_id"),
                "message_id": self.get_extra("napcat_message_id"),
                "user_id": self.get_extra("napcat_user_id"),
                "likes": serialized_likes,
            }
            is_add = getattr(raw_event, "is_add", None)
            if is_add is not None:
                info["is_add"] = is_add
            return info

        if notice_type == "reaction":
            return {
                "notice_type": notice_type,
                "group_id": self.get_extra("napcat_group_id"),
                "message_id": self.get_extra("napcat_message_id"),
                "operator_id": self.get_extra("napcat_operator_id"),
                "code": self.get_extra("napcat_code"),
                "count": self.get_extra("napcat_count"),
                "sub_type": self.get_extra("onebot_sub_type"),
            }

        return None

    def get_notify_info(self) -> dict[str, object] | None:
        if not self.is_notice_type("notify"):
            return None

        info: dict[str, object] = {
            "notice_type": "notify",
            "sub_type": self.get_extra("onebot_sub_type"),
            "user_id": self.get_extra("napcat_user_id"),
            "sender_id": self.get_extra("napcat_sender_id"),
            "group_id": self.get_extra("napcat_group_id"),
            "peer_id": self.get_extra("napcat_peer_id"),
            "target_id": self.get_extra("napcat_target_id"),
            "operator_id": self.get_extra("napcat_operator_id"),
            "operator_nick": self.get_extra("napcat_operator_nick"),
            "honor_type": self.get_extra("napcat_honor_type"),
            "times": self.get_extra("napcat_times"),
            "event_type": self.get_extra("napcat_event_type"),
            "status_text": self.get_extra("napcat_status_text"),
            "busi_id": self.get_extra("napcat_busi_id"),
            "content": self.get_extra("napcat_content"),
            "name_new": self.get_extra("napcat_name_new"),
            "title": self.get_extra("napcat_title"),
        }
        return {key: value for key, value in info.items() if value is not None}

    def get_group_admin_info(self) -> dict[str, object] | None:
        if not self.is_notice_type("group_admin"):
            return None

        return {
            "notice_type": "group_admin",
            "sub_type": self.get_extra("onebot_sub_type"),
            "group_id": self.get_extra("napcat_group_id"),
            "user_id": self.get_extra("napcat_user_id"),
        }

    def get_group_ban_info(self) -> dict[str, object] | None:
        if not self.is_notice_type("group_ban"):
            return None

        return {
            "notice_type": "group_ban",
            "sub_type": self.get_extra("onebot_sub_type"),
            "group_id": self.get_extra("napcat_group_id"),
            "user_id": self.get_extra("napcat_user_id"),
            "operator_id": self.get_extra("napcat_operator_id"),
            "duration": self.get_extra("napcat_duration"),
        }

    def get_group_card_info(self) -> dict[str, object] | None:
        if not self.is_notice_type("group_card"):
            return None

        raw_event = getattr(self.message_obj, "raw_message", None)
        info: dict[str, object] = {
            "notice_type": "group_card",
            "group_id": self.get_extra("napcat_group_id"),
            "user_id": self.get_extra("napcat_user_id"),
        }
        card_old = getattr(raw_event, "card_old", None)
        card_new = getattr(raw_event, "card_new", None)
        if card_old is not None:
            info["card_old"] = card_old
        if card_new is not None:
            info["card_new"] = card_new
        return info

    def get_group_increase_info(self) -> dict[str, object] | None:
        if not self.is_notice_type("group_increase"):
            return None

        return {
            "notice_type": "group_increase",
            "sub_type": self.get_extra("onebot_sub_type"),
            "group_id": self.get_extra("napcat_group_id"),
            "user_id": self.get_extra("napcat_user_id"),
            "operator_id": self.get_extra("napcat_operator_id"),
        }

    def get_group_decrease_info(self) -> dict[str, object] | None:
        if not self.is_notice_type("group_decrease"):
            return None

        return {
            "notice_type": "group_decrease",
            "sub_type": self.get_extra("onebot_sub_type"),
            "group_id": self.get_extra("napcat_group_id"),
            "user_id": self.get_extra("napcat_user_id"),
            "operator_id": self.get_extra("napcat_operator_id"),
        }

    def get_group_essence_info(self) -> dict[str, object] | None:
        if not self.is_notice_type("essence"):
            return None

        raw_event = getattr(self.message_obj, "raw_message", None)
        info: dict[str, object] = {
            "notice_type": "essence",
            "sub_type": self.get_extra("onebot_sub_type"),
            "group_id": self.get_extra("napcat_group_id"),
            "message_id": self.get_extra("napcat_message_id"),
            "operator_id": self.get_extra("napcat_operator_id"),
        }
        sender_id = getattr(raw_event, "sender_id", None)
        if sender_id is not None:
            info["sender_id"] = sender_id
        return info

    def get_request_info(self) -> dict[str, object] | None:
        request_type = self.get_extra("onebot_request_type")
        if request_type not in {"friend", "group"}:
            return None

        info: dict[str, object] = {
            "request_type": request_type,
            "sub_type": self.get_extra("onebot_sub_type"),
            "user_id": self.get_extra("napcat_user_id"),
            "flag": self.get_extra("napcat_flag"),
            "comment": self.get_extra("napcat_comment"),
        }
        group_id = self.get_extra("napcat_group_id")
        if group_id is not None:
            info["group_id"] = group_id
        return {key: value for key, value in info.items() if value is not None}

    async def approve_request(self, *, remark: str | None = None) -> None:
        await self._handle_request(approve=True, remark=remark)

    async def reject_request(self, *, reason: str | None = None) -> None:
        await self._handle_request(approve=False, reason=reason)

    async def get_online_file_messages(
        self,
        *,
        user_id: str | int | None = None,
    ) -> dict[str, object]:
        resolved_user_id = self._resolve_online_file_user_id(user_id=user_id)
        return await self._adapter.client.get_online_file_messages(
            user_id=resolved_user_id
        )

    async def create_flash_task(
        self,
        files: list[str] | str,
        *,
        name: str | None = None,
        thumb_path: str | None = None,
    ) -> dict[str, object]:
        return await self._adapter.client.create_flash_task(
            files=files,
            name=name,
            thumb_path=thumb_path,
        )

    async def get_flash_file_list(
        self,
        fileset_id: str,
    ) -> dict[str, object]:
        return await self._adapter.client.get_flash_file_list(fileset_id=fileset_id)

    async def get_flash_file_url(
        self,
        fileset_id: str,
        *,
        file_name: str | None = None,
        file_index: int | float | None = None,
    ) -> dict[str, object]:
        return await self._adapter.client.get_flash_file_url(
            fileset_id=fileset_id,
            file_name=file_name,
            file_index=file_index,
        )

    async def receive_online_file(
        self,
        *,
        user_id: str | int | None = None,
        msg_id: str | None = None,
        element_id: str | None = None,
    ) -> dict[str, object]:
        resolved_user_id, resolved_msg_id, resolved_element_id = (
            self._resolve_online_file_target(
                user_id=user_id,
                msg_id=msg_id,
                element_id=element_id,
                require_element_id=True,
            )
        )
        return await self._adapter.client.receive_online_file(
            user_id=resolved_user_id,
            msg_id=resolved_msg_id,
            element_id=resolved_element_id,
        )

    async def refuse_online_file(
        self,
        *,
        user_id: str | int | None = None,
        msg_id: str | None = None,
        element_id: str | None = None,
    ) -> dict[str, object]:
        resolved_user_id, resolved_msg_id, resolved_element_id = (
            self._resolve_online_file_target(
                user_id=user_id,
                msg_id=msg_id,
                element_id=element_id,
                require_element_id=True,
            )
        )
        return await self._adapter.client.refuse_online_file(
            user_id=resolved_user_id,
            msg_id=resolved_msg_id,
            element_id=resolved_element_id,
        )

    async def cancel_online_file(
        self,
        *,
        user_id: str | int | None = None,
        msg_id: str | None = None,
    ) -> dict[str, object]:
        resolved_user_id, resolved_msg_id, _ = self._resolve_online_file_target(
            user_id=user_id,
            msg_id=msg_id,
            element_id=None,
            require_element_id=False,
        )
        return await self._adapter.client.cancel_online_file(
            user_id=resolved_user_id,
            msg_id=resolved_msg_id,
        )

    async def send_online_file(
        self,
        file_path: str,
        *,
        file_name: str | None = None,
        user_id: str | int | None = None,
    ) -> dict[str, object]:
        resolved_user_id = self._resolve_online_file_user_id(user_id=user_id)
        return await self._adapter.client.send_online_file(
            user_id=resolved_user_id,
            file_path=file_path,
            file_name=file_name,
        )

    async def send_online_folder(
        self,
        folder_path: str,
        *,
        folder_name: str | None = None,
        user_id: str | int | None = None,
    ) -> dict[str, object]:
        resolved_user_id = self._resolve_online_file_user_id(user_id=user_id)
        return await self._adapter.client.send_online_folder(
            user_id=resolved_user_id,
            folder_path=folder_path,
            folder_name=folder_name,
        )

    async def send_flash_message(
        self,
        fileset_id: str,
    ) -> dict[str, object]:
        if self.get_message_type() == MessageType.GROUP_MESSAGE:
            group_id = self.get_group_id().strip()
            if not group_id:
                raise ValueError("group_id is required for group flash messages")
            return await self._adapter.client.send_flash_message(
                fileset_id=fileset_id,
                group_id=group_id,
            )

        user_id = self.get_sender_id().strip()
        if not user_id:
            raise ValueError("user_id is required for private flash messages")
        return await self._adapter.client.send_flash_message(
            fileset_id=fileset_id,
            user_id=user_id,
        )

    async def set_group_admin(
        self,
        *,
        enable: bool = True,
        user_id: str | int | None = None,
        group_id: str | int | None = None,
    ) -> dict[str, object]:
        resolved_group_id = self._resolve_group_id(group_id)
        resolved_user_id = self._resolve_user_id(user_id)
        return await self._adapter.client.set_group_admin(
            group_id=resolved_group_id,
            user_id=resolved_user_id,
            enable=enable,
        )

    async def set_group_ban(
        self,
        *,
        duration: int | float = 0,
        user_id: str | int | None = None,
        group_id: str | int | None = None,
    ) -> dict[str, object]:
        resolved_group_id = self._resolve_group_id(group_id)
        resolved_user_id = self._resolve_user_id(user_id)
        return await self._adapter.client.set_group_ban(
            group_id=resolved_group_id,
            user_id=resolved_user_id,
            duration=duration,
        )

    async def set_group_card(
        self,
        card: str | None = None,
        *,
        user_id: str | int | None = None,
        group_id: str | int | None = None,
    ) -> dict[str, object]:
        resolved_group_id = self._resolve_group_id(group_id)
        resolved_user_id = self._resolve_user_id(user_id)
        return await self._adapter.client.set_group_card(
            group_id=resolved_group_id,
            user_id=resolved_user_id,
            card=card,
        )

    async def kick_group_member(
        self,
        *,
        user_id: str | int | None = None,
        group_id: str | int | None = None,
        reject_add_request: bool | None = None,
    ) -> dict[str, object]:
        resolved_group_id = self._resolve_group_id(group_id)
        resolved_user_id = self._resolve_user_id(user_id)
        return await self._adapter.client.set_group_kick(
            group_id=resolved_group_id,
            user_id=resolved_user_id,
            reject_add_request=reject_add_request,
        )

    async def kick_group_members(
        self,
        user_ids: list[str | int],
        *,
        group_id: str | int | None = None,
        reject_add_request: bool | None = None,
    ) -> dict[str, object]:
        if not user_ids:
            raise ValueError("user_ids is required for NapCat batch group kicks")

        resolved_group_id = self._resolve_group_id(group_id)
        return await self._adapter.client.set_group_kick_members(
            group_id=resolved_group_id,
            user_ids=user_ids,
            reject_add_request=reject_add_request,
        )

    async def leave_group(
        self,
        *,
        group_id: str | int | None = None,
        is_dismiss: bool | None = None,
    ) -> dict[str, object]:
        resolved_group_id = self._resolve_group_id(group_id)
        return await self._adapter.client.set_group_leave(
            group_id=resolved_group_id,
            is_dismiss=is_dismiss,
        )

    async def set_group_whole_ban(
        self,
        *,
        enable: bool = True,
        group_id: str | int | None = None,
    ) -> dict[str, object]:
        resolved_group_id = self._resolve_group_id(group_id)
        return await self._adapter.client.set_group_whole_ban(
            group_id=resolved_group_id,
            enable=enable,
        )

    async def set_essence_message(
        self,
        message_id: str | int | float | None = None,
    ) -> dict[str, object]:
        resolved_message_id = self._resolve_message_id(message_id)
        return await self._adapter.client.set_essence_message(
            message_id=resolved_message_id,
        )

    async def delete_essence_message(
        self,
        *,
        message_id: str | int | float | None = None,
        msg_seq: str | None = None,
        msg_random: str | None = None,
        group_id: str | int | None = None,
    ) -> dict[str, object]:
        if message_id is None and msg_seq is None and msg_random is None:
            message_id = self._resolve_message_id(None)

        resolved_group_id = str(group_id).strip() if group_id is not None else ""
        if not resolved_group_id:
            resolved_group_id = self.get_group_id().strip()

        return await self._adapter.client.delete_essence_message(
            message_id=message_id,
            msg_seq=msg_seq,
            msg_random=msg_random,
            group_id=resolved_group_id or None,
        )

    async def send_group_notice(
        self,
        content: str,
        *,
        group_id: str | int | None = None,
        pinned: int | float | None = None,
        type_: int | float | None = None,
        confirm_required: int | float | None = None,
        is_show_edit_card: int | float | None = None,
        tip_window_type: int | float | None = None,
        image: str | None = None,
    ) -> dict[str, object]:
        resolved_group_id = self._resolve_group_id(group_id)
        return await self._adapter.client.send_group_notice(
            group_id=resolved_group_id,
            content=content,
            pinned=pinned,
            type_=type_,
            confirm_required=confirm_required,
            is_show_edit_card=is_show_edit_card,
            tip_window_type=tip_window_type,
            image=image,
        )

    async def send_like(
        self,
        *,
        user_id: str | int | None = None,
        times: int | float = 1,
    ) -> dict[str, object]:
        resolved_user_id = self._resolve_user_id(user_id)
        return await self._adapter.client.send_like(
            user_id=resolved_user_id,
            times=times,
        )

    async def send_poke(
        self,
        *,
        user_id: str | int | None = None,
        group_id: str | int | None = None,
        target_id: str | int | None = None,
    ) -> dict[str, object]:
        resolved_user_id = self._resolve_user_id(user_id)
        resolved_group_id = str(group_id).strip() if group_id is not None else ""
        if not resolved_group_id:
            resolved_group_id = self.get_group_id().strip()

        if resolved_group_id:
            return await self._adapter.client.group_poke(
                user_id=resolved_user_id,
                group_id=resolved_group_id,
                target_id=target_id,
            )
        return await self._adapter.client.friend_poke(
            user_id=resolved_user_id,
            target_id=target_id,
        )

    async def set_input_status(
        self,
        *,
        user_id: str | int | None = None,
        event_type: int | float = 1,
    ) -> dict[str, object]:
        resolved_user_id = self._resolve_user_id(user_id)
        return await self._adapter.client.set_input_status(
            user_id=resolved_user_id,
            event_type=event_type,
        )

    async def get_group_msg_history(
        self,
        *,
        group_id: str | int | None = None,
        count: int = 20,
        message_seq: int | str | None = None,
    ) -> list[dict[str, object]]:
        resolved_group_id = self._resolve_group_id(group_id)
        return await self._adapter.client.get_group_msg_history(
            group_id=resolved_group_id,
            count=count,
            message_seq=message_seq,
        )

    async def get_friend_msg_history(
        self,
        *,
        user_id: str | int | None = None,
        count: int = 20,
        message_seq: int | str | None = None,
    ) -> list[dict[str, object]]:
        resolved_user_id = self._resolve_user_id(user_id)
        return await self._adapter.client.get_friend_msg_history(
            user_id=resolved_user_id,
            count=count,
            message_seq=message_seq,
        )

    async def fetch_custom_face(self, *, count: int = 48) -> list[object]:
        return await self._adapter.client.fetch_custom_face(count=count)

    async def get_ai_characters(
        self,
        *,
        group_id: str | int | None = None,
        chat_type: int | float = 1,
    ) -> list[object]:
        resolved_group_id = self._resolve_group_id(group_id)
        return await self._adapter.client.get_ai_characters(
            group_id=resolved_group_id,
            chat_type=chat_type,
        )

    async def send_group_ai_record(
        self,
        text: str,
        *,
        character: str,
        group_id: str | int | None = None,
        chat_type: int | float = 1,
        timeout_seconds: float = 10.0,
    ) -> dict[str, object]:
        resolved_group_id = self._resolve_group_id(group_id)
        return await self._adapter.client.send_group_ai_record(
            group_id=resolved_group_id,
            character=character,
            text=text,
            chat_type=chat_type,
            timeout_seconds=timeout_seconds,
        )

    async def send_typing(self) -> None:
        if not self.is_private_chat():
            return
        await self.set_input_status(event_type=1)

    async def stop_typing(self) -> None:
        if not self.is_private_chat():
            return
        await self.set_input_status(event_type=2)

    async def _handle_request(
        self,
        *,
        approve: bool,
        reason: str | None = None,
        remark: str | None = None,
    ) -> None:
        request_type = self.get_extra("onebot_request_type")
        if request_type not in {"friend", "group"}:
            raise ValueError(
                "approve_request()/reject_request() are only available for NapCat request events"
            )

        raw_event = getattr(self.message_obj, "raw_message", None)
        flag = str(getattr(raw_event, "flag", "")).strip() if raw_event else ""
        if not flag:
            raise ValueError("current NapCat request event does not contain a flag")

        if request_type == "friend":
            if reason is not None:
                raise ValueError("friend add requests do not support a reject reason")
            await self._adapter.client.set_friend_add_request(
                flag=flag,
                approve=approve,
                remark=remark,
            )
            return

        if remark is not None:
            raise ValueError("group add requests do not support a remark")
        await self._adapter.client.set_group_add_request(
            flag=flag,
            approve=approve,
            reason=reason,
        )

    def _resolve_online_file_target(
        self,
        *,
        user_id: str | int | None,
        msg_id: str | None,
        element_id: str | None,
        require_element_id: bool,
    ) -> tuple[str, str, str]:
        resolved_user_id = self._resolve_online_file_user_id(user_id=user_id)
        resolved_msg_id = str(msg_id).strip() if msg_id is not None else ""
        resolved_element_id = str(element_id).strip() if element_id is not None else ""

        first_online_file = next(
            (
                component
                for component in self.get_messages()
                if isinstance(component, OnlineFile)
            ),
            None,
        )
        if first_online_file is not None:
            if not resolved_msg_id:
                resolved_msg_id = first_online_file.msg_id
            if not resolved_element_id:
                resolved_element_id = first_online_file.element_id

        if not resolved_msg_id:
            raise ValueError("msg_id is required for NapCat online file operations")
        if require_element_id and not resolved_element_id:
            raise ValueError("element_id is required for NapCat online file operations")
        return resolved_user_id, resolved_msg_id, resolved_element_id

    def _resolve_online_file_user_id(self, *, user_id: str | int | None) -> str:
        resolved_user_id = str(user_id).strip() if user_id is not None else ""
        if resolved_user_id:
            return resolved_user_id

        peer_id = str(self.get_extra("napcat_peer_id") or "").strip()
        if peer_id:
            return peer_id

        if self.is_private_chat():
            sender_id = self.get_sender_id().strip()
            if sender_id:
                return sender_id

        raise ValueError(
            "user_id is required for NapCat online file operations outside private chats"
        )

    def _resolve_group_id(self, group_id: str | int | None) -> str:
        resolved_group_id = str(group_id).strip() if group_id is not None else ""
        if not resolved_group_id:
            resolved_group_id = self.get_group_id().strip()
        if not resolved_group_id:
            raise ValueError("group_id is required for NapCat group operations")
        return resolved_group_id

    def _resolve_user_id(self, user_id: str | int | None) -> str:
        resolved_user_id = str(user_id).strip() if user_id is not None else ""
        if not resolved_user_id:
            resolved_user_id = self.get_sender_id().strip()
        if not resolved_user_id:
            raise ValueError("user_id is required for NapCat user operations")
        return resolved_user_id

    def _resolve_message_id(self, message_id: str | int | float | None) -> str:
        resolved_message_id = str(message_id).strip() if message_id is not None else ""
        if not resolved_message_id:
            resolved_message_id = str(
                getattr(self.message_obj, "message_id", "")
            ).strip()
        if not resolved_message_id:
            raise ValueError("message_id is required for NapCat message operations")
        return resolved_message_id

    def _attrs_or_mapping_to_dict(self, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return dict(value)
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        if hasattr(value, "__dict__"):
            return {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        return value

    async def get_forward_msg(
        self,
        forward_id: str | int | None = None,
    ) -> dict[str, object] | None:
        resolved_id = str(forward_id).strip() if forward_id is not None else ""
        if not resolved_id:
            for component in self.get_messages():
                if isinstance(component, Forward):
                    resolved_id = str(component.id).strip()
                    if resolved_id:
                        break
        if not resolved_id:
            return None
        return await self._adapter.client.get_forward_message(resolved_id)

    async def get_group(self, group_id=None, **kwargs):
        """Get OneBot group details while preserving inbound data on failures.

        Args:
            group_id: Optional OneBot group identifier.
            **kwargs: Optional ``no_cache`` forwarded to member-list lookup.

        Returns:
            Enriched group information, or a basic group when an API is unavailable.
        """
        resolved_group_id = str(group_id) if group_id else self.get_group_id()
        if not resolved_group_id:
            return None

        current_group = self.message_obj.group
        group = (
            current_group
            if current_group and current_group.group_id == resolved_group_id
            else Group(group_id=resolved_group_id)
        )

        def _value(item: object, field: str):
            if isinstance(item, Mapping):
                value = item.get(field)
            else:
                value = getattr(item, field, None)
            return (
                None if value is None or value.__class__.__name__ == "Unset" else value
            )

        try:
            info = await self._adapter.client.get_group_info(group_id=resolved_group_id)
        except Exception as exc:
            logger.warning(
                "[napcat] Failed to get group information for %s: %s",
                resolved_group_id,
                exc,
            )
            info = None

        if info is not None:
            info_group_id = _value(info, "group_id")
            info_group_name = _value(info, "group_name")
            if isinstance(info_group_id, float | int):
                group.group_id = str(int(info_group_id))
            if info_group_name is not None:
                group.group_name = str(info_group_name)
            member_count = _value(info, "member_count")
            if member_count is not None:
                try:
                    group.member_count = int(member_count)
                except TypeError, ValueError:
                    logger.warning(
                        "[napcat] Invalid member_count for group %s",
                        resolved_group_id,
                    )

        try:
            members = await self._adapter.client.get_group_member_list(
                resolved_group_id,
                no_cache=kwargs.get("no_cache"),
            )
        except Exception as exc:
            logger.warning(
                "[napcat] Failed to get members for group %s: %s",
                resolved_group_id,
                exc,
            )
            return group
        if not isinstance(members, list):
            return group

        owner_id = None
        admin_ids: list[str] = []
        group_members: list[MessageMember] = []
        for member in members:
            user_id = _value(member, "user_id")
            if user_id is None:
                continue
            role = _value(member, "role")
            if role == "owner":
                owner_id = str(int(user_id))
            elif role == "admin":
                admin_ids.append(str(int(user_id)))

            nickname = _value(member, "card") or _value(member, "nickname")
            group_members.append(
                MessageMember(
                    user_id=str(int(user_id)),
                    nickname=str(nickname) if nickname is not None else None,
                )
            )

        group.group_owner = owner_id
        group.group_admins = admin_ids
        group.members = group_members
        if group.member_count is None:
            group.member_count = len(group_members)
        return group

    async def send_streaming(self, generator, use_fallback: bool = False):
        return await self.send_non_streaming_response(
            generator,
            use_fallback=use_fallback,
            component_delay=1.2,
            sleep=asyncio.sleep,
        )
