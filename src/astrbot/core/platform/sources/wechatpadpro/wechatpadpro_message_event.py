import asyncio
import base64
import io
from typing import TYPE_CHECKING

import aiohttp
from PIL import Image as PILImage  # 使用别名避免冲突

from astrbot import logger
from astrbot.core.message.components import (
    Image,
    Plain,
    WechatEmoji,
    Record,
)  # Import Image
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.utils.tencent_record_helper import audio_to_tencent_silk_base64

if TYPE_CHECKING:
    from .wechatpadpro_adapter import WeChatPadProAdapter


class WeChatPadProMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        adapter: "WeChatPadProAdapter",  # 传递适配器实例
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.message_obj = message_obj  # Save the full message object
        self.adapter = adapter  # Save the adapter instance

    async def send(self, message: MessageChain):
        async with aiohttp.ClientSession() as session:
            for comp in message.chain:
                await asyncio.sleep(1)
                if isinstance(comp, Plain):
                    await self._send_text(session, comp.text)
                elif isinstance(comp, Image):
                    await self._send_image(session, comp)
                elif isinstance(comp, WechatEmoji):
                    await self._send_emoji(session, comp)
                elif isinstance(comp, Record):
                    await self._send_voice(session, comp)
        await super().send(message)

    async def _send_image(self, session: aiohttp.ClientSession, comp: Image):
        b64 = await comp.convert_to_base64()
        raw = self._validate_base64(b64)
        b64c = self._compress_image(raw)
        payload = {
            "MsgItem": [
                {"ImageContent": b64c, "MsgType": 3, "ToUserName": self.session_id}
            ]
        }
        url = f"{self.adapter.base_url}/message/SendImageNewMessage"
        await self._post(session, url, payload)

    async def _send_text(self, session: aiohttp.ClientSession, text: str):
        if (
            self.message_obj.type == MessageType.GROUP_MESSAGE  # 确保是群聊消息
            and self.adapter.settings.get(
                "reply_with_mention", False
            )  # 检查适配器设置是否启用 reply_with_mention
            and self.message_obj.sender  # 确保有发送者信息
            and (
                self.message_obj.sender.user_id or self.message_obj.sender.nickname
            )  # 确保发送者有 ID 或昵称
        ):
            # 优先使用 nickname，如果没有则使用 user_id
            mention_text = (
                self.message_obj.sender.nickname or self.message_obj.sender.user_id
            )
            message_text = f"@{mention_text} {text}"
            # logger.info(f"已添加 @ 信息: {message_text}")
        else:
            message_text = text
        if self.get_group_id() and "#" in self.session_id:
            session_id = self.session_id.split("#")[0]
        else:
            session_id = self.session_id
        payload = {
            "MsgItem": [
                {
                    "MsgType": 1,
                    "TextContent": message_text,
                    "ToUserName": session_id,
                }
            ]
        }
        url = f"{self.adapter.base_url}/message/SendTextMessage"
        await self._post(session, url, payload)

    async def _send_emoji(self, session: aiohttp.ClientSession, comp: WechatEmoji):
        payload = {
            "EmojiList": [
                {
                    "EmojiMd5": comp.md5,
                    "EmojiSize": comp.md5_len,
                    "ToUserName": self.session_id,
                }
            ]
        }
        url = f"{self.adapter.base_url}/message/SendEmojiMessage"
        await self._post(session, url, payload)

    async def _send_voice(self, session: aiohttp.ClientSession, comp: Record):
        record_path = await comp.convert_to_file_path()
        # 默认已经存在 data/temp 中
        b64, duration = await audio_to_tencent_silk_base64(record_path)
        payload = {
            "ToUserName": self.session_id,
            "VoiceData": b64,
            "VoiceFormat": 4,
            "VoiceSecond": duration,
        }
        url = f"{self.adapter.base_url}/message/SendVoice"
        await self._post(session, url, payload)

    @staticmethod
    def _validate_base64(b64: str) -> bytes:
        return base64.b64decode(b64, validate=True)

    @staticmethod
    def _compress_image(data: bytes) -> str:
        img = PILImage.open(io.BytesIO(data))
        buf = io.BytesIO()
        if img.format == "JPEG":
            img.save(buf, "JPEG", quality=80)
        else:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(buf, "JPEG", quality=80)
        # logger.info("图片处理完成！！！")
        return base64.b64encode(buf.getvalue()).decode()

    async def _post(self, session, url, payload):
        params = {"key": self.adapter.auth_key}
        try:
            async with session.post(url, params=params, json=payload) as resp:
                data = await resp.json()
                if resp.status != 200 or data.get("Code") != 200:
                    logger.error(f"{url} failed: {resp.status} {data}")
        except Exception as e:
            logger.error(f"{url} error: {e}")


# TODO: 添加对其他消息组件类型的处理 (Record, Video, At等)
# elif isinstance(component, Record):
#     pass
# elif isinstance(component, Video):
#     pass
# elif isinstance(component, At):
#     pass
# ...
