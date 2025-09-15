from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import PlatformMetadata, AstrBotMessage
from astrbot.api.message_components import Plain


def _serialize_message_chain_simple(chain):
    """简单的消息链序列化"""
    content = ""
    has_at = False

    for item in chain:
        if isinstance(item, Plain):
            content += item.text
        elif hasattr(item, "content") and item.content:
            for sub_item in item.content:
                content += getattr(sub_item, "text", "")
        else:
            text = getattr(item, "text", "")
            if text:
                content += text
                if "@" in text:
                    has_at = True

    return content, has_at


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
        content, has_at = _serialize_message_chain_simple(message.chain)

        if not content:
            logger.debug("[MisskeyEvent] 内容为空，跳过发送")
            return

        try:
            original_message_id = getattr(self.message_obj, "message_id", None)

            raw_message = getattr(self.message_obj, "raw_message", {})
            if raw_message and not has_at:
                user_data = raw_message.get("user", {})
                username = user_data.get("username", "")
                if username and not content.startswith(f"@{username}"):
                    content = f"@{username} {content}"

            if original_message_id and hasattr(self.client, "create_note"):
                # 简化的可见性处理
                visibility = "public"
                visible_user_ids = None

                if raw_message:
                    original_visibility = raw_message.get("visibility", "public")
                    if original_visibility == "specified":
                        visibility = "specified"
                        original_visible_users = raw_message.get("visibleUserIds", [])
                        sender_id = raw_message.get("userId", "")
                        users_to_include = [sender_id] if sender_id else []
                        visible_user_ids = list(
                            set(original_visible_users + users_to_include)
                        )
                        visible_user_ids = [uid for uid in visible_user_ids if uid]
                    else:
                        visibility = original_visibility

                await self.client.create_note(
                    content,
                    reply_id=original_message_id,
                    visibility=visibility,
                    visible_user_ids=visible_user_ids,
                )
            elif hasattr(self.client, "send_message") and self.session_id:
                sid = str(self.session_id)
                if 5 <= len(sid) <= 64 and " " not in sid:
                    logger.debug(f"[MisskeyEvent] 发送私信: {sid}")
                    await self.client.send_message(sid, content)
                    return
                elif hasattr(self.client, "create_note"):
                    logger.debug("[MisskeyEvent] 创建新帖子")
                    await self.client.create_note(content)

            await super().send(message)

        except Exception as e:
            logger.error(f"[MisskeyEvent] 发送失败: {e}")
