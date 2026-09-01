import re
from collections.abc import AsyncGenerator

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import AstrBotMessage, Group, MessageMember, PlatformMetadata
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.utils.error_redaction import safe_error

from .misskey_utils import (
    add_at_mention_if_needed,
    extract_room_id_from_session_id,
    extract_user_id_from_session_id,
    is_valid_room_session_id,
    is_valid_user_session_id,
    resolve_message_visibility,
    serialize_message_chain,
)


class MisskeyPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._client = client

    def _is_system_command(self, message_str: str) -> bool:
        """检测是否为系统指令"""
        if not message_str or not message_str.strip():
            return False

        system_prefixes = ["/", "!", "#", ".", "^"]
        message_trimmed = message_str.strip()

        return any(message_trimmed.startswith(prefix) for prefix in system_prefixes)

    async def send(self, message: MessageChain) -> PlatformSendResult | None:
        """发送消息，使用适配器的完整上传和发送逻辑"""
        try:
            logger.debug(
                f"[MisskeyEvent] send 方法被调用，消息链包含 {len(message.chain)} 个组件",
            )

            # 使用适配器的 send_by_session 方法，它包含文件上传逻辑
            from astrbot.core.platform.message_session import MessageSession
            from astrbot.core.platform.message_type import MessageType

            # 根据session_id类型确定消息类型
            if is_valid_user_session_id(self.session_id):
                message_type = MessageType.FRIEND_MESSAGE
            elif is_valid_room_session_id(self.session_id):
                message_type = MessageType.GROUP_MESSAGE
            else:
                message_type = MessageType.FRIEND_MESSAGE  # 默认

            session = MessageSession(
                platform_name=self.platform_meta.name,
                message_type=message_type,
                session_id=self.session_id,
            )

            logger.debug(
                f"[MisskeyEvent] 检查适配器方法: hasattr(self._client, 'send_by_session') = {hasattr(self._client, 'send_by_session')}",
            )

            # 调用适配器的 send_by_session 方法
            if hasattr(self._client, "send_by_session"):
                logger.debug("[MisskeyEvent] 调用适配器的 send_by_session 方法")
                await self._client.send_by_session(session, message)
            else:
                # 回退到原来的简化发送逻辑
                content, has_at = serialize_message_chain(message.chain)

                if not content:
                    logger.debug("[MisskeyEvent] 内容为空，跳过发送")
                    return

                original_message_id = getattr(self.message_obj, "message_id", None)
                raw_message = getattr(self.message_obj, "raw_message", {})

                if raw_message and not has_at:
                    user_data = raw_message.get("user", {})
                    user_info = {
                        "username": user_data.get("username", ""),
                        "nickname": user_data.get(
                            "name",
                            user_data.get("username", ""),
                        ),
                    }
                    content = add_at_mention_if_needed(content, user_info, has_at)

                # 根据会话类型选择发送方式
                if hasattr(self._client, "send_message") and is_valid_user_session_id(
                    self.session_id,
                ):
                    user_id = extract_user_id_from_session_id(self.session_id)
                    await self._client.send_message(user_id, content)
                elif hasattr(
                    self._client,
                    "send_room_message",
                ) and is_valid_room_session_id(self.session_id):
                    room_id = extract_room_id_from_session_id(self.session_id)
                    await self._client.send_room_message(room_id, content)
                elif original_message_id and hasattr(self._client, "create_note"):
                    visibility, visible_user_ids = resolve_message_visibility(
                        raw_message=raw_message,
                    )
                    await self._client.create_note(
                        content,
                        reply_id=original_message_id,
                        visibility=visibility,
                        visible_user_ids=visible_user_ids,
                    )
                elif hasattr(self._client, "create_note"):
                    logger.debug("[MisskeyEvent] 创建新帖子")
                    await self._client.create_note(content)

            return await super().send(message)

        except Exception as e:
            logger.error(f"[MisskeyEvent] 发送失败: {e}")

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain],
        use_fallback: bool = False,
    ):
        return await self.send_non_streaming_response(
            generator,
            use_fallback=use_fallback,
            sentence_pattern=re.compile(r"[^。？！~…]+[。？！~…]+"),
        )

    async def get_group(
        self,
        group_id: str | None = None,
        **kwargs,
    ) -> Group | None:
        """Retrieve Misskey chat room information and all room members.

        Args:
            group_id: Room ID to query. Defaults to the current room ID.
            **kwargs: Reserved for compatibility with the platform event interface.

        Returns:
            Room information, or ``None`` when no room ID is available. If the
            instance does not support the room APIs, returns the basic room
            information already present on the incoming message.
        """
        del kwargs
        room_id = str(group_id or self.get_group_id() or "")
        if not room_id:
            return None

        fallback_group = Group.from_inbound(self.message_obj.group, room_id)
        cached_room = getattr(self._client, "_user_cache", {}).get(
            f"room:{room_id}",
            {},
        )
        if not fallback_group.group_name:
            fallback_group.group_name = cached_room.get("room_name") or None
        if not fallback_group.group_owner:
            fallback_group.group_owner = str(cached_room.get("owner_id") or "") or None

        api = getattr(self._client, "api", None)
        if api is None or not hasattr(api, "_make_request"):
            return fallback_group

        try:
            room = await api._make_request(
                "chat/rooms/show",
                {"roomId": room_id},
            )
            if not isinstance(room, dict):
                raise TypeError("Misskey room response must be an object")

            memberships: list[dict] = []
            until_id = None
            while True:
                payload = {"roomId": room_id, "limit": 100}
                if until_id:
                    payload["untilId"] = until_id
                page = await api._make_request("chat/rooms/members", payload)
                if not isinstance(page, list):
                    raise TypeError("Misskey room members response must be a list")
                memberships.extend(
                    membership for membership in page if isinstance(membership, dict)
                )
                if len(page) < 100:
                    break
                next_until_id = page[-1].get("id")
                if not next_until_id or next_until_id == until_id:
                    raise ValueError(
                        "Misskey room members pagination cursor is missing"
                    )
                until_id = next_until_id
        except Exception as exc:
            logger.warning(
                "[MisskeyEvent] Failed to retrieve room information for %s: %s",
                room_id,
                safe_error("", exc),
            )
            return fallback_group

        owner_id = str(room.get("ownerId") or fallback_group.group_owner or "")
        members = []
        member_ids = set()
        for membership in memberships:
            user = membership.get("user")
            user = user if isinstance(user, dict) else {}
            user_id = str(membership.get("userId") or user.get("id") or "")
            if not user_id or user_id in member_ids:
                continue
            member_ids.add(user_id)
            members.append(
                MessageMember(
                    user_id=user_id,
                    nickname=user.get("name") or user.get("username") or None,
                ),
            )

        # Misskey does not create a membership record for the room owner.
        if owner_id and owner_id not in member_ids:
            owner = room.get("owner")
            owner = owner if isinstance(owner, dict) else {}
            members.append(
                MessageMember(
                    user_id=owner_id,
                    nickname=owner.get("name") or owner.get("username") or None,
                ),
            )

        group = Group(
            group_id=room_id,
            group_name=room.get("name") or fallback_group.group_name,
            group_owner=owner_id or None,
            group_admins=[],
            members=members,
            member_count=len(members),
        )
        return group
