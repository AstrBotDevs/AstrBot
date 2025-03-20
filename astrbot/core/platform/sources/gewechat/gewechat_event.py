import wave
import uuid
import traceback
import os
from astrbot.core.utils.io import save_temp_img, download_image_by_url, download_file
from astrbot.core.utils.tencent_record_helper import wav_to_tencent_silk
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image, Record, At, File
from .client import SimpleGewechatClient


def get_wav_duration(file_path):
    with wave.open(file_path, "rb") as wav_file:
        file_size = os.path.getsize(file_path)
        n_channels, sampwidth, framerate, n_frames = wav_file.getparams()[:4]
        if n_frames == 2147483647:
            duration = (file_size - 44) / (n_channels * sampwidth * framerate)
        elif n_frames == 0:
            duration = (file_size - 44) / (n_channels * sampwidth * framerate)
        else:
            duration = n_frames / float(framerate)
        return duration


class GewechatPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: SimpleGewechatClient,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    @staticmethod
    async def send_with_client(
        message: MessageChain, to_wxid: str, client: SimpleGewechatClient
    ):
        if not to_wxid:
            logger.error("无法获取到 to_wxid。")
            return

        #  检查@
        ats = []
        ats_names = []
        for comp in message.chain:
            if isinstance(comp, At):
                ats.append(comp.qq)
                ats_names.append(comp.name)
        has_at = False

        for comp in message.chain:
            if isinstance(comp, Plain):
                text = comp.text
                payload = {
                    "to_wxid": to_wxid,
                    "content": text,
                }
                if not has_at and ats:
                    ats = f"{','.join(ats)}"
                    ats_names = f"@{' @'.join(ats_names)}"
                    text = f"{ats_names} {text}"
                    payload["content"] = text
                    payload["ats"] = ats
                    has_at = True
                await client.post_text(**payload)

            elif isinstance(comp, Image):
                img_path = await comp.convert_to_file_path()

                # 检查 record_path 是否在 data/temp 目录中
                temp_directory = os.path.abspath("data/temp")
                if os.path.commonpath([temp_directory, img_path]) != temp_directory:
                    with open(img_path, "rb") as f:
                        img_path = save_temp_img(f.read())

                file_id = os.path.basename(img_path)
                img_url = f"{client.file_server_url}/{file_id}"
                logger.debug(f"gewe callback img url: {img_url}")
                await client.post_image(to_wxid, img_url)
            elif isinstance(comp, Record):
                # 默认已经存在 data/temp 中
                record_url = comp.file
                record_path = await comp.convert_to_file_path()

                silk_path = f"data/temp/{uuid.uuid4()}.silk"
                try:
                    duration = await wav_to_tencent_silk(record_path, silk_path)
                except Exception as e:
                    logger.error(traceback.format_exc())
                    await client.post_text(to_wxid, f"语音文件转换失败。{str(e)}")
                logger.info("Silk 语音文件格式转换至: " + record_path)
                if duration == 0:
                    duration = get_wav_duration(record_path)
                file_id = os.path.basename(silk_path)
                record_url = f"{client.file_server_url}/{file_id}"
                logger.debug(f"gewe callback record url: {record_url}")
                await client.post_voice(to_wxid, record_url, duration * 1000)
            elif isinstance(comp, File):
                file_path = comp.file
                file_name = comp.name
                if file_path.startswith("file:///"):
                    file_path = file_path[8:]
                elif file_path.startswith("http"):
                    await download_file(file_path, f"data/temp/{file_name}")
                else:
                    file_path = file_path

                file_id = os.path.basename(file_path)
                file_url = f"{client.file_server_url}/{file_id}"
                logger.debug(f"gewe callback file url: {file_url}")
                await client.post_file(to_wxid, file_url, file_id)
            elif isinstance(comp, At):
                pass
            else:
                logger.debug(f"gewechat 忽略: {comp.type}")

    async def send(self, message: MessageChain):
        to_wxid = self.message_obj.raw_message.get("to_wxid", None)
        await GewechatPlatformEvent.send_with_client(message, to_wxid, self.client)
        await super().send(message)
