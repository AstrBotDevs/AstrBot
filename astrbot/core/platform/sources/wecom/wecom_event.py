import asyncio
import os

from wechatpy.enterprise import WeChatClient
from wechatpy.exceptions import WeChatClientException

from astrbot import logger
from astrbot.core.message.components import File, Image, Plain, Record, Video
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import AstrBotMessage, PlatformMetadata
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.send_result import PlatformSendResult
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
        self._client = client

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

    async def _send_plain_text(
        self,
        text: str,
        sender_id: str,
        recipient_id: str,
        kf_message_api: WeChatKFMessage | None,
    ) -> None:
        """Send split text through the selected WeCom messaging mode."""
        for chunk in await self.split_plain(text):
            if kf_message_api is None:
                self._client.message.send_text(sender_id, recipient_id, chunk)
            else:
                try:
                    kf_message_api.send_text(recipient_id, sender_id, chunk)
                except WeChatClientException as exc:
                    if getattr(exc, "errcode", None) != 40096:
                        raise
                    logger.warning(
                        "kf API error 40096 for user %s, falling back to regular "
                        "message API",
                        recipient_id,
                    )
                    self._client.message.send_text(sender_id, recipient_id, chunk)
            await asyncio.sleep(0.5)

    async def _send_upload_error(
        self,
        error_text: str,
        sender_id: str,
        recipient_id: str,
        kf_message_api: WeChatKFMessage | None,
    ) -> None:
        """Report an upload failure without recursively entering ``send``."""
        await self._send_plain_text(
            error_text,
            sender_id,
            recipient_id,
            kf_message_api,
        )
        await super().send(MessageChain().message(error_text))

    async def _upload_and_send_media(
        self,
        path: str,
        media_type: str,
        sender_id: str,
        recipient_id: str,
        kf_message_api: WeChatKFMessage | None,
    ) -> bool:
        """Upload one media file and deliver it through the selected mode."""
        mode_label = "微信客服" if kf_message_api else "企业微信"
        media_label = {
            "image": "图片",
            "voice": "语音",
            "file": "文件",
            "video": "视频",
        }[media_type]
        try:
            with open(path, "rb") as media_file:
                response = self._client.media.upload(media_type, media_file)
        except Exception as exc:
            error_text = f"{mode_label}上传{media_label}失败: {exc}"
            logger.error(error_text)
            await self._send_upload_error(
                error_text,
                sender_id,
                recipient_id,
                kf_message_api,
            )
            return False

        if media_type == "voice":
            logger.info(f"{mode_label}上传语音返回: {response}")
        else:
            logger.debug(f"{mode_label}上传{media_label}返回: {response}")
        media_id = response["media_id"]
        if kf_message_api:
            match media_type:
                case "image":
                    kf_message_api.send_image(recipient_id, sender_id, media_id)
                case "voice":
                    kf_message_api.send_voice(recipient_id, sender_id, media_id)
                case "file":
                    kf_message_api.send_file(recipient_id, sender_id, media_id)
                case _:
                    kf_message_api.send_video(recipient_id, sender_id, media_id)
        else:
            match media_type:
                case "image":
                    self._client.message.send_image(sender_id, recipient_id, media_id)
                case "voice":
                    self._client.message.send_voice(sender_id, recipient_id, media_id)
                case "file":
                    self._client.message.send_file(sender_id, recipient_id, media_id)
                case _:
                    self._client.message.send_video(sender_id, recipient_id, media_id)
        return True

    async def _send_media(
        self,
        component: Image | Record | File | Video,
        sender_id: str,
        recipient_id: str,
        kf_message_api: WeChatKFMessage | None,
    ) -> bool:
        """Prepare, upload, and send a supported media component."""
        if isinstance(component, Image):
            return await self._upload_and_send_media(
                await component.convert_to_file_path(),
                "image",
                sender_id,
                recipient_id,
                kf_message_api,
            )
        if isinstance(component, File):
            return await self._upload_and_send_media(
                await component.get_file(),
                "file",
                sender_id,
                recipient_id,
                kf_message_api,
            )
        if isinstance(component, Video):
            return await self._upload_and_send_media(
                await component.convert_to_file_path(),
                "video",
                sender_id,
                recipient_id,
                kf_message_api,
            )

        record_path = await component.convert_to_file_path()
        record_path_amr = await convert_audio_to_amr(record_path)
        try:
            return await self._upload_and_send_media(
                record_path_amr,
                "voice",
                sender_id,
                recipient_id,
                kf_message_api,
            )
        finally:
            if record_path_amr != record_path and os.path.exists(record_path_amr):
                try:
                    os.remove(record_path_amr)
                except OSError as exc:
                    logger.warning(f"删除临时音频文件失败: {exc}")

    async def send(self, message: MessageChain) -> PlatformSendResult | None:
        """Send a message through customer-service or application mode."""
        kf_message_api = getattr(self._client, "kf_message", None)
        if hasattr(self._client, "kf_message") and not isinstance(
            kf_message_api, WeChatKFMessage
        ):
            logger.warning("未找到微信客服发送消息方法。")
            return

        if kf_message_api:
            sender_id = self.get_self_id()
            recipient_id = self.get_sender_id()
        else:
            sender_id = self.message_obj.self_id
            recipient_id = self.message_obj.session_id

        for component in message.chain:
            if isinstance(component, Plain):
                await self._send_plain_text(
                    component.text,
                    sender_id,
                    recipient_id,
                    kf_message_api,
                )
            elif isinstance(component, Image | Record | File | Video):
                if not await self._send_media(
                    component,
                    sender_id,
                    recipient_id,
                    kf_message_api,
                ):
                    return
            else:
                logger.warning(f"还没实现这个消息类型的发送逻辑: {component.type}。")

        return await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        return await self._send_buffered_streaming_response(generator, use_fallback)
