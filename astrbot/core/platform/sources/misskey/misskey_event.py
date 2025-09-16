from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import PlatformMetadata, AstrBotMessage

from .misskey_utils import (
    serialize_message_chain,
    resolve_visibility_from_raw_message,
    is_valid_user_session_id,
    add_at_mention_if_needed,
)


class MisskeyPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    async def send(self, message: MessageChain):
        content, has_at = serialize_message_chain(message.chain)

        if not content:
            logger.debug("[MisskeyEvent] 内容为空，跳过发送")
            return

        try:
            original_message_id = getattr(self.message_obj, "message_id", None)
            raw_message = getattr(self.message_obj, "raw_message", {})

            if raw_message and not has_at:
                user_data = raw_message.get("user", {})
                user_info = {
                    "username": user_data.get("username", ""),
                    "nickname": user_data.get("name", user_data.get("username", "")),
                }
                content = add_at_mention_if_needed(content, user_info, has_at)

            if original_message_id and hasattr(self.client, "create_note"):
                visibility, visible_user_ids = resolve_visibility_from_raw_message(
                    raw_message
                )

                await self.client.create_note(
                    content,
                    reply_id=original_message_id,
                    visibility=visibility,
                    visible_user_ids=visible_user_ids,
                )
            elif hasattr(self.client, "send_message") and is_valid_user_session_id(
                self.session_id
            ):
                logger.debug(f"[MisskeyEvent] 发送私信: {self.session_id}")
                await self.client.send_message(str(self.session_id), content)
                return
            elif hasattr(self.client, "create_note"):
                logger.debug("[MisskeyEvent] 创建新帖子")
                await self.client.create_note(content)

            await super().send(message)

        except Exception as e:
            logger.error(f"[MisskeyEvent] 发送失败: {e}")
