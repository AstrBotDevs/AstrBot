import asyncio
import os
import uuid

from wechatpy.enterprise import WeChatClient
from wechatpy.exceptions import WeChatClientException

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    ActionRow,
    ButtonStyle,
    CallbackAction,
    File,
    Image,
    Plain,
    Record,
    UrlAction,
    Video,
)
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.core.platform.button_interaction import encode_button_callback
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
                logger.warning("未找到微信客服发送消息方法。")
                return

            user_id = self.get_sender_id()
            for comp in message.chain:
                if isinstance(comp, Plain):
                    # Split long text messages if needed
                    plain_chunks = await self.split_plain(comp.text)
                    for chunk in plain_chunks:
                        try:
                            kf_message_api.send_text(user_id, self.get_self_id(), chunk)
                        except WeChatClientException as e:
                            if getattr(e, "errcode", None) == 40096:
                                # 40096: invalid external userid, fallback to regular message API
                                logger.warning(
                                    f"kf API error 40096 for user {user_id}, falling back to regular message API"
                                )
                                self.client.message.send_text(
                                    self.get_self_id(), user_id, chunk
                                )
                            else:
                                raise
                        await asyncio.sleep(0.5)  # Avoid sending too fast
                elif isinstance(comp, Image):
                    img_path = await comp.convert_to_file_path()

                    with open(img_path, "rb") as f:
                        try:
                            response = self.client.media.upload("image", f)
                        except Exception as e:
                            logger.error(f"微信客服上传图片失败: {e}")
                            await self.send(
                                MessageChain().message(f"微信客服上传图片失败: {e}"),
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
                    record_path_amr = await convert_audio_to_amr(record_path)

                    try:
                        with open(record_path_amr, "rb") as f:
                            try:
                                response = self.client.media.upload("voice", f)
                            except Exception as e:
                                logger.error(f"微信客服上传语音失败: {e}")
                                await self.send(
                                    MessageChain().message(
                                        f"微信客服上传语音失败: {e}"
                                    ),
                                )
                                return
                            logger.info(f"微信客服上传语音返回: {response}")
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
                                logger.warning(f"删除临时音频文件失败: {e}")
                elif isinstance(comp, File):
                    file_path = await comp.get_file()

                    with open(file_path, "rb") as f:
                        try:
                            response = self.client.media.upload("file", f)
                        except Exception as e:
                            logger.error(f"微信客服上传文件失败: {e}")
                            await self.send(
                                MessageChain().message(f"微信客服上传文件失败: {e}"),
                            )
                            return
                        logger.debug(f"微信客服上传文件返回: {response}")
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
                            logger.error(f"微信客服上传视频失败: {e}")
                            await self.send(
                                MessageChain().message(f"微信客服上传视频失败: {e}"),
                            )
                            return
                        logger.debug(f"微信客服上传视频返回: {response}")
                        kf_message_api.send_video(
                            user_id,
                            self.get_self_id(),
                            response["media_id"],
                        )
                elif isinstance(comp, ActionRow):
                    if not comp.buttons:
                        continue
                    menu_list = []
                    for button in comp.buttons:
                        if isinstance(button.action, CallbackAction):
                            callback_id = encode_button_callback(
                                button.id,
                                button.action.data,
                            )
                            if len(callback_id.encode("utf-8")) > 64:
                                raise ValueError(
                                    "WeCom customer-service callback IDs cannot exceed "
                                    "64 bytes."
                                )
                            menu_list.append(
                                {
                                    "type": "click",
                                    "click": {
                                        "id": callback_id,
                                        "content": button.label,
                                    },
                                }
                            )
                        elif isinstance(button.action, UrlAction):
                            menu_list.append(
                                {
                                    "type": "view",
                                    "view": {
                                        "url": button.action.url,
                                        "content": button.label,
                                    },
                                }
                            )
                    kf_message_api.send_msgmenu(
                        user_id,
                        self.get_self_id(),
                        comp.fallback_text or "",
                        menu_list,
                        "",
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
                            logger.error(f"企业微信上传图片失败: {e}")
                            await self.send(
                                MessageChain().message(f"企业微信上传图片失败: {e}"),
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
                    record_path_amr = await convert_audio_to_amr(record_path)

                    try:
                        with open(record_path_amr, "rb") as f:
                            try:
                                response = self.client.media.upload("voice", f)
                            except Exception as e:
                                logger.error(f"企业微信上传语音失败: {e}")
                                await self.send(
                                    MessageChain().message(
                                        f"企业微信上传语音失败: {e}"
                                    ),
                                )
                                return
                            logger.info(f"企业微信上传语音返回: {response}")
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
                                logger.warning(f"删除临时音频文件失败: {e}")
                elif isinstance(comp, File):
                    file_path = await comp.get_file()

                    with open(file_path, "rb") as f:
                        try:
                            response = self.client.media.upload("file", f)
                        except Exception as e:
                            logger.error(f"企业微信上传文件失败: {e}")
                            await self.send(
                                MessageChain().message(f"企业微信上传文件失败: {e}"),
                            )
                            return
                        logger.debug(f"企业微信上传文件返回: {response}")
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
                            logger.error(f"企业微信上传视频失败: {e}")
                            await self.send(
                                MessageChain().message(f"企业微信上传视频失败: {e}"),
                            )
                            return
                        logger.debug(f"企业微信上传视频返回: {response}")
                        self.client.message.send_video(
                            message_obj.self_id,
                            message_obj.session_id,
                            response["media_id"],
                        )
                elif isinstance(comp, ActionRow):
                    if not comp.buttons:
                        continue
                    if len(comp.buttons) > 6:
                        raise ValueError(
                            "WeCom template cards support at most 6 buttons."
                        )
                    style_map = {
                        ButtonStyle.DEFAULT: 1,
                        ButtonStyle.PRIMARY: 2,
                        ButtonStyle.DANGER: 3,
                        ButtonStyle.SUCCESS: 4,
                    }
                    button_list = []
                    for button in comp.buttons:
                        item = {
                            "text": button.label,
                            "style": style_map[button.style],
                        }
                        if isinstance(button.action, CallbackAction):
                            item["type"] = 0
                            item["key"] = encode_button_callback(
                                button.id,
                                button.action.data,
                            )
                        elif isinstance(button.action, UrlAction):
                            item["type"] = 1
                            item["url"] = button.action.url
                        button_list.append(item)
                    self.client.message.send(
                        message_obj.self_id,
                        message_obj.session_id,
                        msg={
                            "msgtype": "template_card",
                            "template_card": {
                                "card_type": "button_interaction",
                                "main_title": {
                                    "title": comp.fallback_text or "请选择操作"
                                },
                                "button_list": button_list,
                                "task_id": f"astrbot_{uuid.uuid4().hex}",
                            },
                        },
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
            return None
        buffer.squash_plain()
        await self.send(buffer)
        return await super().send_streaming(generator, use_fallback)
