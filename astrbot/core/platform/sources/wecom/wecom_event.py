from astrbot.core.lang import t
import asyncio
import os

from wechatpy.enterprise import WeChatClient

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import File, Image, Plain, Record, Video
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.core.utils.media_utils import convert_audio_to_amr

from .wecom_kf_message import WeChatKFMessage


class WecomPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: WeChatClient,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    @staticmethod
    async def send_with_client(
        client: WeChatClient,
        message: MessageChain,
        user_name: str,
    ) -> None:
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

    async def send(self, message: MessageChain) -> None:
        message_obj = self.message_obj

        is_wechat_kf = hasattr(self.client, "kf_message")
        if is_wechat_kf:
            # 微信客服
            kf_message_api = getattr(self.client, "kf_message", None)
            if not isinstance(kf_message_api, WeChatKFMessage):
                logger.warning(t("msg-e164c137"))
                return

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
                            logger.error(t("msg-c114425e", e=e))
                            await self.send(
                                MessageChain().message(t("msg-c114425e", e=e)),
                            )
                            return
                        logger.debug(t("msg-a90bc15d", response=response))
                        kf_message_api.send_image(
                            user_id,
                            self.get_self_id(),
                            response["media_id"],
                        )
                elif isinstance(comp, Record):
                    record_path = await comp.convert_to_file_path()
                    record_path_amr = await convert_audio_to_amr(record_path)

                    try:
                        with open(record_path_amr, "rb") as f:
                            try:
                                response = self.client.media.upload("voice", f)
                            except Exception as e:
                                logger.error(t("msg-38298880", e=e))
                                await self.send(
                                    MessageChain().message(
                                        t("msg-38298880", e=e)
                                    ),
                                )
                                return
                            logger.info(t("msg-3aee0caa", response=response))
                            kf_message_api.send_voice(
                                user_id,
                                self.get_self_id(),
                                response["media_id"],
                            )
                    finally:
                        if record_path_amr != record_path and os.path.exists(
                            record_path_amr,
                        ):
                            try:
                                os.remove(record_path_amr)
                            except OSError as e:
                                logger.warning(t("msg-15e6381b", e=e))
                elif isinstance(comp, File):
                    file_path = await comp.get_file()

                    with open(file_path, "rb") as f:
                        try:
                            response = self.client.media.upload("file", f)
                        except Exception as e:
                            logger.error(t("msg-a79ae417", e=e))
                            await self.send(
                                MessageChain().message(t("msg-a79ae417", e=e)),
                            )
                            return
                        logger.debug(t("msg-374455ef", response=response))
                        kf_message_api.send_file(
                            user_id,
                            self.get_self_id(),
                            response["media_id"],
                        )
                elif isinstance(comp, Video):
                    video_path = await comp.convert_to_file_path()

                    with open(video_path, "rb") as f:
                        try:
                            response = self.client.media.upload("video", f)
                        except Exception as e:
                            logger.error(t("msg-a2a133e4", e=e))
                            await self.send(
                                MessageChain().message(t("msg-a2a133e4", e=e)),
                            )
                            return
                        logger.debug(t("msg-2732fffd", response=response))
                        kf_message_api.send_video(
                            user_id,
                            self.get_self_id(),
                            response["media_id"],
                        )
                else:
                    logger.warning(t("msg-60815f02", res=comp.type))
        else:
            # 企业微信应用
            for comp in message.chain:
                if isinstance(comp, Plain):
                    # Split long text messages if needed
                    plain_chunks = await self.split_plain(comp.text)
                    for chunk in plain_chunks:
                        self.client.message.send_text(
                            message_obj.self_id,
                            message_obj.session_id,
                            chunk,
                        )
                        await asyncio.sleep(0.5)  # Avoid sending too fast
                elif isinstance(comp, Image):
                    img_path = await comp.convert_to_file_path()

                    with open(img_path, "rb") as f:
                        try:
                            response = self.client.media.upload("image", f)
                        except Exception as e:
                            logger.error(t("msg-9913aa52", e=e))
                            await self.send(
                                MessageChain().message(t("msg-9913aa52", e=e)),
                            )
                            return
                        logger.debug(t("msg-9e90ba91", response=response))
                        self.client.message.send_image(
                            message_obj.self_id,
                            message_obj.session_id,
                            response["media_id"],
                        )
                elif isinstance(comp, Record):
                    record_path = await comp.convert_to_file_path()
                    record_path_amr = await convert_audio_to_amr(record_path)

                    try:
                        with open(record_path_amr, "rb") as f:
                            try:
                                response = self.client.media.upload("voice", f)
                            except Exception as e:
                                logger.error(t("msg-232af016", e=e))
                                await self.send(
                                    MessageChain().message(
                                        t("msg-232af016", e=e)
                                    ),
                                )
                                return
                            logger.info(t("msg-e5b8829d", response=response))
                            self.client.message.send_voice(
                                message_obj.self_id,
                                message_obj.session_id,
                                response["media_id"],
                            )
                    finally:
                        if record_path_amr != record_path and os.path.exists(
                            record_path_amr,
                        ):
                            try:
                                os.remove(record_path_amr)
                            except OSError as e:
                                logger.warning(t("msg-15e6381b", e=e))
                elif isinstance(comp, File):
                    file_path = await comp.get_file()

                    with open(file_path, "rb") as f:
                        try:
                            response = self.client.media.upload("file", f)
                        except Exception as e:
                            logger.error(t("msg-f68671d7", e=e))
                            await self.send(
                                MessageChain().message(t("msg-f68671d7", e=e)),
                            )
                            return
                        logger.debug(t("msg-8cdcc397", response=response))
                        self.client.message.send_file(
                            message_obj.self_id,
                            message_obj.session_id,
                            response["media_id"],
                        )
                elif isinstance(comp, Video):
                    video_path = await comp.convert_to_file_path()

                    with open(video_path, "rb") as f:
                        try:
                            response = self.client.media.upload("video", f)
                        except Exception as e:
                            logger.error(t("msg-4f3e15f5", e=e))
                            await self.send(
                                MessageChain().message(t("msg-4f3e15f5", e=e)),
                            )
                            return
                        logger.debug(t("msg-4e9aceea", response=response))
                        self.client.message.send_video(
                            message_obj.self_id,
                            message_obj.session_id,
                            response["media_id"],
                        )
                else:
                    logger.warning(t("msg-60815f02", res=comp.type))

        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
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
