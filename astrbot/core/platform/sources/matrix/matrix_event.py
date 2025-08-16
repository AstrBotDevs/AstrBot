import sys
from astrbot.api import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Image, File
import aiohttp
import os

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class MatrixMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj,
        platform_meta: PlatformMetadata,
        session_id: str,
        client,
        room_id: str = None,
        event_id: str = None,
    ):
        super().__init__(
            message_str=message_str,
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id=session_id,
        )
        self.client = client
        self.room_id = room_id
        self.event_id = event_id

    @override
    async def send(self, message: MessageChain):
        """发送消息到 Matrix 房间"""
        if not self.room_id or not self.client:
            logger.error("Matrix 房间 ID 或客户端不可用")
            return

        for message_component in message:
            try:
                if isinstance(message_component, Plain):
                    # 发送纯文本消息
                    await self.client.room_send(
                        room_id=self.room_id,
                        message_type="m.room.message",
                        content={
                            "msgtype": "m.text",
                            "body": message_component.text,
                        },
                    )
                    logger.debug(
                        f"Matrix 文本消息已发送: {message_component.text[:100]}..."
                    )

                elif isinstance(message_component, Image):
                    # 发送图片消息
                    try:
                        if message_component.file:
                            # 从文件路径读取
                            image_path = message_component.file
                        elif message_component.url:
                            # 从URL下载
                            image_path = await self._download_image(
                                message_component.url
                            )
                        else:
                            logger.error("Matrix 图片消息缺少文件或URL")
                            continue

                        if os.path.exists(image_path):
                            # 上传图片到 Matrix
                            with open(image_path, "rb") as f:
                                response = await self.client.upload(
                                    data_provider=f,
                                    content_type="image/jpeg",
                                    filename=os.path.basename(image_path),
                                )

                            if response:
                                await self.client.room_send(
                                    room_id=self.room_id,
                                    message_type="m.room.message",
                                    content={
                                        "msgtype": "m.image",
                                        "body": message_component.filename
                                        or "image.jpg",
                                        "url": response.content_uri,
                                    },
                                )
                                logger.debug("Matrix 图片消息已发送")
                        else:
                            logger.error(f"Matrix 图片文件不存在: {image_path}")

                    except Exception as e:
                        logger.error(f"Matrix 图片处理失败: {e}")
                        continue

                elif isinstance(message_component, File):
                    # 发送文件消息
                    try:
                        file_path = message_component.name
                        if os.path.exists(file_path):
                            with open(file_path, "rb") as f:
                                response = await self.client.upload(
                                    data_provider=f,
                                    content_type="application/octet-stream",
                                    filename=os.path.basename(file_path),
                                )

                            if response:
                                await self.client.room_send(
                                    room_id=self.room_id,
                                    message_type="m.room.message",
                                    content={
                                        "msgtype": "m.file",
                                        "body": os.path.basename(file_path),
                                        "url": response.content_uri,
                                    },
                                )
                                logger.debug("Matrix 文件消息已发送")
                    except Exception as e:
                        logger.error(f"Matrix 文件处理失败: {e}")
                        continue

            except Exception as e:
                logger.error(f"Matrix 消息发送失败: {e}")

    async def _download_image(self, url: str) -> str:
        """下载图片到临时文件"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        temp_path = f"/tmp/matrix_image_{self.event_id}.jpg"
                        with open(temp_path, "wb") as f:
                            f.write(data)
                        return temp_path
        except Exception as e:
            logger.error(f"Matrix 图片下载失败: {e}")
        return ""
