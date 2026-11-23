import asyncio
from typing import Any

import aiofiles
import anyio
from wechatpy import WeChatClient
from wechatpy.replies import ImageReply, VoiceReply

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    ActionRow,
    Button,
    Image,
    Plain,
    Record,
)
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.core.platform.sources.weixin_shared import split_weixin_text
from astrbot.core.utils.media_utils import convert_audio_to_amr


class WeixinOfficialAccountPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: WeChatClient,
        message_out: dict[Any, Any],
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client
        self.message_out = message_out

    @staticmethod
    async def send_with_client(
        client: WeChatClient,
        message: MessageChain,
        user_name: str,
    ) -> None:
        pass

    async def split_plain(self, plain: str, max_length: int = 1024) -> list[str]:
        return split_weixin_text(plain, max_length)

    async def send(self, message: MessageChain) -> None:
        message_obj = self.message_obj
        active_send_mode = message_obj.raw_message.get("active_send_mode", False)
        for comp in message.chain:
            if isinstance(comp, ActionRow):
                fallback_parts = [
                    f"{button.label}: {button.action.url}"
                    for button in comp.buttons
                    if isinstance(button.action, Button.UrlAction)
                ]
                callback_labels = [
                    button.label
                    for button in comp.buttons
                    if isinstance(button.action, Button.CallbackAction)
                ]
                if callback_labels:
                    fallback_parts.append(
                        comp.fallback_text
                        or (
                            f"可选操作：{' / '.join(callback_labels)}"
                            "（当前平台不支持按钮，请发送选项名称）"
                        )
                    )
                if not fallback_parts:
                    continue
                comp = Plain("\n".join(fallback_parts))

            if isinstance(comp, Plain):
                plain_chunks = await self.split_plain(comp.text)
                if active_send_mode:
                    for chunk in plain_chunks:
                        self.client.message.send_text(message_obj.sender.user_id, chunk)
                else:
                    logger.debug(
                        f"split plain into {len(plain_chunks)} chunks for passive reply. Message not sent.",
                    )
                    self.message_out.setdefault("cached_xml", []).extend(plain_chunks)
            elif isinstance(comp, Image):
                img_path = await comp.convert_to_file_path()
                async with aiofiles.open(img_path, "rb") as f:
                    try:
                        response = self.client.media.upload("image", f)
                    except Exception as e:
                        logger.error(f"微信公众平台上传图片失败: {e}")
                        await self.send(
                            MessageChain().message(f"微信公众平台上传图片失败: {e}"),
                        )
                        return
                    logger.debug(f"微信公众平台上传图片返回: {response}")
                    if active_send_mode:
                        self.client.message.send_image(
                            message_obj.sender.user_id,
                            response["media_id"],
                        )
                    else:
                        reply = ImageReply(
                            media_id=response["media_id"],
                            message=self.message_obj.raw_message["message"],
                        )
                        xml = reply.render()
                        future = self.message_obj.raw_message["future"]
                        assert isinstance(future, asyncio.Future)
                        future.set_result(xml)
            elif isinstance(comp, Record):
                record_path = await comp.convert_to_file_path()
                record_path_amr = await convert_audio_to_amr(record_path)
                try:
                    async with aiofiles.open(record_path_amr, "rb") as f:
                        try:
                            response = self.client.media.upload("voice", f)
                        except Exception as e:
                            logger.error(f"微信公众平台上传语音失败: {e}")
                            await self.send(
                                MessageChain().message(
                                    f"微信公众平台上传语音失败: {e}",
                                ),
                            )
                            return
                        logger.info(f"微信公众平台上传语音返回: {response}")
                        if active_send_mode:
                            self.client.message.send_voice(
                                message_obj.sender.user_id,
                                response["media_id"],
                            )
                        else:
                            reply = VoiceReply(
                                media_id=response["media_id"],
                                message=self.message_obj.raw_message["message"],
                            )
                            xml = reply.render()
                            future = self.message_obj.raw_message["future"]
                            assert isinstance(future, asyncio.Future)
                            future.set_result(xml)
                finally:
                    if (
                        record_path_amr != record_path
                        and await anyio.Path(record_path_amr).exists()
                    ):
                        try:
                            await anyio.Path(record_path_amr).unlink()
                        except OSError as e:
                            logger.warning(f"删除临时音频文件失败: {e}")
            else:
                logger.warning(f"还没实现这个消息类型的发送逻辑: {comp.type}｡")
        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        return await self._send_buffered_stream(
            generator, use_fallback, super().send_streaming
        )
