import asyncio
import re
from collections.abc import AsyncGenerator

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata

from .misskey_utils import (
    add_at_mention_if_needed,
    extract_room_id_from_session_id,
    extract_user_id_from_session_id,
    is_valid_room_session_id,
    is_valid_user_session_id,
    resolve_visibility_from_raw_message,
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
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    def _is_system_command(self, message_str: str) -> bool:
        """检测是否为系统指令"""
        if not message_str or not message_str.strip():
            return False

        system_prefixes = ["/", "!", "#", ".", "^"]
        message_trimmed = message_str.strip()

        return any(message_trimmed.startswith(prefix) for prefix in system_prefixes)

    async def send(self, message: MessageChain):
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
                f"[MisskeyEvent] 检查适配器方法: hasattr(self.client, 'send_by_session') = {hasattr(self.client, 'send_by_session')}",
            )

            # 调用适配器的 send_by_session 方法
            if hasattr(self.client, "send_by_session"):
                logger.debug("[MisskeyEvent] 调用适配器的 send_by_session 方法")
                await self.client.send_by_session(session, message)
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
                if hasattr(self.client, "send_message") and is_valid_user_session_id(
                    self.session_id,
                ):
                    user_id = extract_user_id_from_session_id(self.session_id)
                    await self.client.send_message(user_id, content)
                elif hasattr(
                    self.client,
                    "send_room_message",
                ) and is_valid_room_session_id(self.session_id):
                    room_id = extract_room_id_from_session_id(self.session_id)
                    await self.client.send_room_message(room_id, content)
                elif original_message_id and hasattr(self.client, "create_note"):
                    visibility, visible_user_ids = resolve_visibility_from_raw_message(
                        raw_message,
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

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain, None],
        use_fallback: bool = False,
    ):
        if not use_fallback:
            buffer = None
            async for chain in generator:
                if not buffer:
                    buffer = chain
                else:
                    buffer.chain.extend(chain.chain)
            if not buffer:
                return None
            buffer.squash_plain()
            await self.send(buffer)
            return await super().send_streaming(generator, use_fallback)

        buffer = ""
        pattern = re.compile(r"[^。？！~…]+[。？！~…]+")

        async for chain in generator:
            if isinstance(chain, MessageChain):
                for comp in chain.chain:
                    if isinstance(comp, Plain):
                        buffer += comp.text
                        if any(p in buffer for p in "。？！~…"):
                            buffer = await self.process_buffer(buffer, pattern)
                    else:
                        await self.send(MessageChain(chain=[comp]))
                        await asyncio.sleep(1.5)  # 限速

        if buffer.strip():
            await self.send(MessageChain([Plain(buffer)]))
        return await super().send_streaming(generator, use_fallback)
