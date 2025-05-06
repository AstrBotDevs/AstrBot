import asyncio
import re
import wave
import uuid
import traceback
import os

from typing import AsyncGenerator
from astrbot.core.utils.io import save_temp_img, download_file
from astrbot.core.utils.tencent_record_helper import wav_to_tencent_silk
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata, Group, MessageMember
from astrbot.api.message_components import (
    Plain,
    Image,
    Record,
    At,
    File,
    Video,
    WechatEmoji as Emoji,
)
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
                # 为了安全，向 AstrBot 回调服务注册可被 gewechat 访问的文件，并获得文件 token
                token = await client._register_file(img_path)
                img_url = f"{client.file_server_url}/{token}"
                logger.debug(f"gewe callback img url: {img_url}")
                await client.post_image(to_wxid, img_url)
            elif isinstance(comp, Video):
                if comp.cover != "":
                    await client.forward_video(to_wxid, comp.cover)
                else:
                    try:
                        from pyffmpeg import FFmpeg
                    except (ImportError, ModuleNotFoundError):
                        logger.error(
                            "需要安装 pyffmpeg 库才能发送视频: pip install pyffmpeg"
                        )
                        raise ModuleNotFoundError(
                            "需要安装 pyffmpeg 库才能发送视频: pip install pyffmpeg"
                        )

                    video_url = comp.file
                    # 根据 url 下载视频
                    if video_url.startswith("http"):
                        video_filename = f"{uuid.uuid4()}.mp4"
                        video_path = f"data/temp/{video_filename}"
                        await download_file(video_url, video_path)
                    else:
                        video_path = video_url

                    video_token = await client._register_file(video_path)
                    video_callback_url = f"{client.file_server_url}/{video_token}"

                    # 获取视频第一帧
                    thumb_path = f"data/temp/gewechat_video_thumb_{uuid.uuid4()}.jpg"

                    video_path = video_path.replace(" ", "\\ ")
                    try:
                        ff = FFmpeg()
                        command = f"-i {video_path} -ss 0 -vframes 1 {thumb_path}"
                        ff.options(command)
                        thumb_token = await client._register_file(thumb_path)
                        thumb_url = f"{client.file_server_url}/{thumb_token}"
                    except Exception as e:
                        logger.error(f"获取视频第一帧失败: {e}")

                    # 获取视频时长
                    try:
                        from pyffmpeg import FFprobe

                        # 创建 FFprobe 实例
                        ffprobe = FFprobe(video_url)
                        # 获取时长字符串
                        duration_str = ffprobe.duration
                        # 处理时长字符串
                        video_duration = float(duration_str.replace(":", ""))
                    except Exception as e:
                        logger.error(f"获取时长失败: {e}")
                        video_duration = 10

                    # 发送视频
                    await client.post_video(
                        to_wxid, video_callback_url, thumb_url, video_duration
                    )

                    # 删除临时缩略图文件
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
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
                token = await client._register_file(silk_path)
                record_url = f"{client.file_server_url}/{token}"
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

                token = await client._register_file(file_path)
                file_url = f"{client.file_server_url}/{token}"
                logger.debug(f"gewe callback file url: {file_url}")
                await client.post_file(to_wxid, file_url, file_name)
            elif isinstance(comp, Emoji):
                await client.post_emoji(to_wxid, comp.md5, comp.md5_len, comp.cdnurl)
            elif isinstance(comp, At):
                pass
            else:
                logger.debug(f"gewechat 忽略: {comp.type}")

    async def send(self, message: MessageChain):
        to_wxid = self.message_obj.raw_message.get("to_wxid", None)
        await GewechatPlatformEvent.send_with_client(message, to_wxid, self.client)
        await super().send(message)

    async def get_group(self, group_id=None, **kwargs):
        # 确定有效的 group_id
        if group_id is None:
            group_id = self.get_group_id()

        if not group_id:
            return None

        res = await self.client.get_group(group_id)
        data: dict = res["data"]

        if not data["chatroomId"]:
            return None

        members = [
            MessageMember(user_id=member["wxid"], nickname=member["nickName"])
            for member in data.get("memberList", [])
        ]

        return Group(
            group_id=data["chatroomId"],
            group_name=data.get("nickName"),
            group_avatar=data.get("smallHeadImgUrl"),
            group_owner=data.get("chatRoomOwner"),
            members=members,
        )

    async def send_streaming(
        self, generator: AsyncGenerator, use_fallback: bool = False
    ):
        if not use_fallback:
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
