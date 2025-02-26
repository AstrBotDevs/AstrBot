import uuid
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image, Record
from wechatpy.enterprise import WeChatClient
from astrbot.core.utils.io import download_image_by_url, download_file

from astrbot.api import logger

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

    async def send(self, message: MessageChain):
        message_obj = self.message_obj

        for comp in message.chain:
            if isinstance(comp, Plain):
                self.client.message.send_text(
                    message_obj.self_id, message_obj.session_id, comp.text
                )
            elif isinstance(comp, Image):
                img_url = comp.file
                img_path = ""
                if img_url.startswith("file:///"):
                    img_path = img_url[8:]
                elif comp.file and comp.file.startswith("http"):
                    img_path = await download_image_by_url(comp.file)
                else:
                    img_path = img_url

                with open(img_path, "rb") as f:
                    try:
                        response = self.client.media.upload("image", f)
                    except Exception as e:
                        logger.error(f"企业微信上传图片失败: {e}")
                        await self.send(
                            MessageChain().message(f"企业微信上传图片失败: {e}")
                        )
                        return
                    logger.info(f"企业微信上传图片返回: {response}")
                    self.client.message.send_image(
                        message_obj.self_id,
                        message_obj.session_id,
                        response["media_id"],
                    )
            elif isinstance(comp, Record):
                record_url = comp.file
                record_path = ""

                if record_url.startswith("file:///"):
                    record_path = record_url[8:]
                elif record_url.startswith("http"):
                    await download_file(record_url, f"data/temp/{uuid.uuid4()}.wav")
                else:
                    record_path = record_url

                # 转成amr
                record_path_amr = f"data/temp/{uuid.uuid4()}.amr"
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

        await super().send(message)
