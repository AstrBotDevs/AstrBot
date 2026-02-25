import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any, cast

from wechatpy import WeChatClient
from wechatpy.replies import ImageReply, VoiceReply

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Image, Plain, Record
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
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
        """将长文本分割成多个小文本, 每个小文本长度不超过 max_length 字符

        Args:
            plain (str): 要分割的长文本
        Returns:
            list[str]: 分割后的文本列表

        """
        if len(plain) <= max_length:
            return [plain]
        result = []
        start = 0
        while start < len(plain):
            # 剩下的字符串长度<max_length时结束
            if start + max_length >= len(plain):
                result.append(plain[start:])
                break

            # 向前搜索分割标点符号
            end = min(start + max_length, len(plain))
            cut_position = end
            for i in range(end, start, -1):
                if i < len(plain) and plain[i - 1] in [
                    "。",
                    "！",
                    "？",
                    ".",
                    "!",
                    "?",
                    "\n",
                    ";",
                    "；",
                ]:
                    cut_position = i
                    break

            # 没找到合适的位置分割, 直接切分
            if cut_position == end and end < len(plain):
                cut_position = end

            result.append(plain[start:cut_position])
            start = cut_position

        return result

    async def send(self, message: MessageChain) -> None:
        message_obj = self.message_obj
        active_send_mode = cast(dict, message_obj.raw_message).get(
            "active_send_mode", False
        )
        for comp in message.chain:
            if isinstance(comp, Plain):
                # Split long text messages if needed
                plain_chunks = await self.split_plain(comp.text)
                if active_send_mode:
                    for chunk in plain_chunks:
                        self.client.message.send_text(message_obj.sender.user_id, chunk)
                else:
                    # disable passive sending, just store the chunks in
                    logger.debug(
                        f"split plain into {len(plain_chunks)} chunks for passive reply. Message not sent."
                    )
                    self.message_out["cached_xml"] = plain_chunks
            elif isinstance(comp, Image):
                img_path = await comp.convert_to_file_path()

                with open(img_path, "rb") as f:
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
                            message=cast(dict, self.message_obj.raw_message)["message"],
                        )
                        xml = reply.render()
                        future = cast(dict, self.message_obj.raw_message)["future"]
                        assert isinstance(future, asyncio.Future)
                        future.set_result(xml)

            elif isinstance(comp, Record):
                record_path = await comp.convert_to_file_path()
                record_path_amr = await convert_audio_to_amr(record_path)

                try:
                    with open(record_path_amr, "rb") as f:
                        try:
                            response = self.client.media.upload("voice", f)
                        except Exception as e:
                            logger.error(f"微信公众平台上传语音失败: {e}")
                            await self.send(
                                MessageChain().message(
                                    f"微信公众平台上传语音失败: {e}"
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
                                message=cast(dict, self.message_obj.raw_message)[
                                    "message"
                                ],
                            )
                            xml = reply.render()
                            future = cast(dict, self.message_obj.raw_message)["future"]
                            assert isinstance(future, asyncio.Future)
                            future.set_result(xml)
                finally:
                    if record_path_amr != record_path and os.path.exists(
                        record_path_amr
                    ):
                        try:
                            os.remove(record_path_amr)
                        except OSError as e:
                            logger.warning(f"删除临时音频文件失败: {e}")

            else:
                logger.warning(f"还没实现这个消息类型的发送逻辑: {comp.type}。")

        await super().send(message)

    async def send_streaming(
        self, generator: AsyncGenerator[MessageChain, None], use_fallback: bool = False
    ):
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
