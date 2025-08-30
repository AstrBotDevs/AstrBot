from typing import Optional

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Image, Reply
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot import logger


class MisskeyPlatformEvent(AstrMessageEvent):
    """Misskey 平台事件处理器"""

    def __init__(
        self,
        message_str: str,
        message_obj: Optional[AstrBotMessage],
        platform_meta: PlatformMetadata,
        session_id: str,
        adapter=None,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.adapter = adapter

    async def send(self, message: MessageChain):
        """发送消息到 Misskey"""
        if not self.adapter:
            logger.error("Misskey adapter not available")
            return

        # 收集文本内容
        text_parts = []
        reply_id = None

        for component in message.chain:
            if isinstance(component, Plain):
                text_parts.append(component.text)
            elif isinstance(component, Reply):
                reply_id = component.id
            elif isinstance(component, Image):
                # 目前暂不支持图片，可以在未来版本中添加
                text_parts.append("[图片]")
            else:
                # 其他类型的消息组件暂时转换为文本描述
                text_parts.append(f"[{type(component).__name__}]")

        if not text_parts:
            logger.warning("No text content to send to Misskey")
            return

        full_text = "".join(text_parts)

        # 如果这是对某条 Note 的回复，尝试获取原始 Note 信息
        original_note = self.get_extra("original_note")
        if original_note and not reply_id:
            reply_id = original_note.get("id")

        try:
            # 发送 Note
            result = await self.adapter.send_note(
                text=full_text, reply_id=reply_id, visibility="public"
            )

            if result:
                logger.info(
                    f"Successfully sent Misskey note: {result.get('id', 'unknown')}"
                )
            else:
                logger.error("Failed to send Misskey note")

        except Exception as e:
            logger.error(f"Error sending message to Misskey: {e}")

        await super().send(message)
