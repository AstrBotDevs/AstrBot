import os
import uuid
import asyncio
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image, Record
from wechatpy.enterprise import WeChatClient
from .wecom_kf_message import WeChatKFMessage

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

try:
    import pydub
except Exception:
    logger.warning(
        "检测到 pydub 库未安装，企业微信将无法语音收发。如需使用语音，请前往管理面板 -> 控制台 -> 安装 Pip 库安装 pydub。"
    )
    pass


class WecomPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: WeChatClient,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    @staticmethod
    async def send_with_client(
        client: WeChatClient, message: MessageChain, user_name: str
    ):
        pass

    async def split_plain(self, plain: str) -> list[str]:
        """将长文本分割成多个小文本, 每个小文本长度不超过 2048 字符

        Args:
            plain (str): 要分割的长文本
        Returns:
            list[str]: 分割后的文本列表
        """
        if len(plain) <= 2048:
            return [plain]
        else:
            result = []
            start = 0
            while start < len(plain):
                # 剩下的字符串长度<2048时结束
                if start + 2048 >= len(plain):
                    result.append(plain[start:])
                    break

                # 向前搜索分割标点符号
                end = min(start + 2048, len(plain))
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

    async def send(self, message: MessageChain):
        message_obj = self.message_obj

        is_wechat_kf = hasattr(self.client, "kf_message")
        if is_wechat_kf:
            # 微信客服
            kf_message_api = getattr(self.client, "kf_message", None)
            if not kf_message_api:
                logger.warning("未找到微信客服发送消息方法。")
                return
            assert isinstance(kf_message_api, WeChatKFMessage)
            user_id = self.get_sender_id()
            for comp in message.chain:
                if isinstance(comp, Plain):
                    # Split long text messages if needed
                    plain_chunks = await self.split_plain(comp.text)
                    for chunk in plain_chunks:
                        kf_message_api.send_text(user_id, self.get_self_id(), chunk)
                        await asyncio.sleep(0.5)  # Avoid sending too fast
                elif isinstance(comp, Image):
                    img_path = await comp.convert_to_file_path()

                    with open(img_path, "rb") as f:
                        try:
                            response = self.client.media.upload("image", f)
                        except Exception as e:
                            logger.error(f"微信客服上传图片失败: {e}")
                            await self.send(
                                MessageChain().message(f"微信客服上传图片失败: {e}")
                            )
                            return
                        logger.debug(f"微信客服上传图片返回: {response}")
                        kf_message_api.send_image(
                            user_id,
                            self.get_self_id(),
                            response["media_id"],
                        )
                elif isinstance(comp, Record):
                    record_path = await comp.convert_to_file_path()
                    # 转成amr
                    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                    record_path_amr = os.path.join(temp_dir, f"{uuid.uuid4()}.amr")
                    pydub.AudioSegment.from_wav(record_path).export(
                        record_path_amr, format="amr"
                    )

                    with open(record_path_amr, "rb") as f:
                        try:
                            response = self.client.media.upload("voice", f)
                        except Exception as e:
                            logger.error(f"微信客服上传语音失败: {e}")
                            await self.send(
                                MessageChain().message(f"微信客服上传语音失败: {e}")
                            )
                            return
                        logger.info(f"微信客服上传语音返回: {response}")
                        kf_message_api.send_voice(
                            user_id,
                            self.get_self_id(),
                            response["media_id"],
                        )
                else:
                    logger.warning(f"还没实现这个消息类型的发送逻辑: {comp.type}。")
        else:
            # 企业微信应用
            for comp in message.chain:
                if isinstance(comp, Plain):
                    # Split long text messages if needed
                    plain_chunks = await self.split_plain(comp.text)
                    for chunk in plain_chunks:
                        self.client.message.send_text(
                            message_obj.self_id, message_obj.session_id, chunk
                        )
                        await asyncio.sleep(0.5)  # Avoid sending too fast
                elif isinstance(comp, Image):
                    img_path = await comp.convert_to_file_path()

                    with open(img_path, "rb") as f:
                        try:
                            response = self.client.media.upload("image", f)
                        except Exception as e:
                            logger.error(f"企业微信上传图片失败: {e}")
                            await self.send(
                                MessageChain().message(f"企业微信上传图片失败: {e}")
                            )
                            return
                        logger.debug(f"企业微信上传图片返回: {response}")
                        self.client.message.send_image(
                            message_obj.self_id,
                            message_obj.session_id,
                            response["media_id"],
                        )
                elif isinstance(comp, Record):
                    record_path = await comp.convert_to_file_path()
                    # 转成amr
                    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                    record_path_amr = os.path.join(temp_dir, f"{uuid.uuid4()}.amr")
                    pydub.AudioSegment.from_wav(record_path).export(
                        record_path_amr, format="amr"
                    )

                    with open(record_path_amr, "rb") as f:
                        try:
                            response = self.client.media.upload("voice", f)
                        except Exception as e:
                            logger.error(f"企业微信上传语音失败: {e}")
                            await self.send(
                                MessageChain().message(f"企业微信上传语音失败: {e}")
                            )
                            return
                        logger.info(f"企业微信上传语音返回: {response}")
                        self.client.message.send_voice(
                            message_obj.self_id,
                            message_obj.session_id,
                            response["media_id"],
                        )
                else:
                    logger.warning(f"还没实现这个消息类型的发送逻辑: {comp.type}。")

        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        buffer = None
        async for chain in generator:
            if not buffer:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)
        if not buffer:
            return
        buffer.squash_plain()
        await self.send(buffer)
        return await super().send_streaming(generator, use_fallback)
