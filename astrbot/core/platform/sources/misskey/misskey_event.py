from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import PlatformMetadata, AstrBotMessage

from .misskey_utils import (
    serialize_message_chain,
    resolve_visibility_from_raw_message,
    is_valid_user_session_id,
    add_at_mention_if_needed,
    extract_user_id_from_session_id,
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

        # 检测系统指令，如果是系统指令则阻止进入LLM对话历史
        if self._is_system_command(message_str):
            self.should_call_llm(True)

    def _is_system_command(self, message_str: str) -> bool:
        """检测是否为系统指令"""
        if not message_str or not message_str.strip():
            return False

        # 常见的系统指令前缀
        system_prefixes = ["/", "!", "#", ".", "^"]
        message_trimmed = message_str.strip()

        # 检查是否以系统指令前缀开头
        for prefix in system_prefixes:
            if message_trimmed.startswith(prefix):
                return True

        return False

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

            # 对于聊天消息（私信），优先使用聊天API
            if hasattr(self.client, "send_message") and is_valid_user_session_id(
                self.session_id
            ):
                user_id = extract_user_id_from_session_id(self.session_id)
                await self.client.send_message(user_id, content)
                return
            elif original_message_id and hasattr(self.client, "create_note"):
                visibility, visible_user_ids = resolve_visibility_from_raw_message(
                    raw_message
                )

                await self.client.create_note(
                    content,
                    reply_id=original_message_id,
                    visibility=visibility,
                    visible_user_ids=visible_user_ids,
                )
            elif hasattr(self.client, "create_note"):
                logger.debug("[MisskeyEvent] 创建新帖子")
                await self.client.create_note(content)

            await super().send(message)

        except Exception as e:
            logger.error(f"[MisskeyEvent] 发送失败: {e}")
