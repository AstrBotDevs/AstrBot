import botpy
import botpy.message
import botpy.types
import botpy.types.message
import asyncio
import base64
import aiofiles
from astrbot.core.utils.io import file_to_base64, download_image_by_url
from astrbot.core.utils.tencent_record_helper import wav_to_tencent_silk
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image, Record
from botpy import Client
from botpy.http import Route
from astrbot.api import logger
from botpy.types.message import Media
from botpy.types import message
from typing import Optional
import random
import uuid
import os


class QQOfficialMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        bot: Client,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.bot = bot
        self.send_buffer = None

    async def send(self, message: MessageChain):
        self.send_buffer = message
        await self._post_send()

    async def send_streaming(self, generator, use_fallback: bool = False):
        """流式输出仅支持消息列表私聊"""
        stream_payload = {"state": 1, "id": None, "index": 0, "reset": False}
        last_edit_time = 0  # 上次编辑消息的时间
        throttle_interval = 1  # 编辑消息的间隔时间 (秒)
        ret = None
        try:
            async for chain in generator:
                source = self.message_obj.raw_message
                if not self.send_buffer:
                    self.send_buffer = chain
                else:
                    self.send_buffer.chain.extend(chain.chain)

                if isinstance(source, botpy.message.C2CMessage):
                    # 真流式传输
                    current_time = asyncio.get_event_loop().time()
                    time_since_last_edit = current_time - last_edit_time

                    if time_since_last_edit >= throttle_interval:
                        ret = await self._post_send(stream=stream_payload)
                        stream_payload["index"] += 1
                        stream_payload["id"] = ret["id"]
                        last_edit_time = asyncio.get_event_loop().time()

            if isinstance(source, botpy.message.C2CMessage):
                # 结束流式对话，并且传输 buffer 中剩余的消息
                stream_payload["state"] = 10
                ret = await self._post_send(stream=stream_payload)

        except Exception as e:
            logger.error(f"发送流式消息时出错: {e}", exc_info=True)
            self.send_buffer = None

        return await super().send_streaming(generator, use_fallback)

    async def _post_send(self, stream: dict = None):
        if not self.send_buffer:
            return

        source = self.message_obj.raw_message
        assert isinstance(
            source,
            (
                botpy.message.Message,
                botpy.message.GroupMessage,
                botpy.message.DirectMessage,
                botpy.message.C2CMessage,
            ),
        )

        (
            plain_text,
            image_base64,
            image_path,
            record_file_path
        ) = await QQOfficialMessageEvent._parse_to_qqofficial(self.send_buffer)

        if not plain_text and not image_base64 and not image_path and not record_file_path:
            return

        payload = {
            "content": plain_text,
            "msg_id": self.message_obj.message_id,
        }

        if not isinstance(source, (botpy.message.Message, botpy.message.DirectMessage)):
            payload["msg_seq"] = random.randint(1, 10000)

        ret = None

        match type(source):
            case botpy.message.GroupMessage:
                if image_base64:
                    media = await self.upload_group_and_c2c_image(
                        image_base64, 1, group_openid=source.group_openid
                    )
                    payload["media"] = media
                    payload["msg_type"] = 7
                if record_file_path: # group record msg
                    media = await self.upload_group_and_c2c_record(
                        record_file_path, 3, group_openid=source.group_openid
                    )
                    payload["media"] = media
                    payload["msg_type"] = 7
                ret = await self.bot.api.post_group_message(
                    group_openid=source.group_openid, **payload
                )
            case botpy.message.C2CMessage:
                if image_base64:
                    media = await self.upload_group_and_c2c_image(
                        image_base64, 1, openid=source.author.user_openid
                    )
                    payload["media"] = media
                    payload["msg_type"] = 7
                if record_file_path: # c2c record
                    media = await self.upload_group_and_c2c_record(
                        record_file_path, 3, openid = source.author.user_openid
                    )
                    payload["media"] = media
                    payload["msg_type"] = 7
                if stream:
                    ret = await self.post_c2c_message(
                        openid=source.author.user_openid,
                        **payload,
                        stream=stream,
                    )
                else:
                    ret = await self.post_c2c_message(
                        openid=source.author.user_openid, **payload
                    )
                logger.debug(f"Message sent to C2C: {ret}")
            case botpy.message.Message:
                if image_path:
                    payload["file_image"] = image_path
                ret = await self.bot.api.post_message(
                    channel_id=source.channel_id, **payload
                )
            case botpy.message.DirectMessage:
                if image_path:
                    payload["file_image"] = image_path
                ret = await self.bot.api.post_dms(guild_id=source.guild_id, **payload)

        await super().send(self.send_buffer)

        self.send_buffer = None

        return ret

    async def upload_group_and_c2c_image(
        self, image_base64: str, file_type: int, **kwargs
    ) -> botpy.types.message.Media:
        payload = {
            "file_data": image_base64,
            "file_type": file_type,
            "srv_send_msg": False,
        }
        if "openid" in kwargs:
            payload["openid"] = kwargs["openid"]
            route = Route("POST", "/v2/users/{openid}/files", openid=kwargs["openid"])
            return await self.bot.api._http.request(route, json=payload)
        elif "group_openid" in kwargs:
            payload["group_openid"] = kwargs["group_openid"]
            route = Route(
                "POST",
                "/v2/groups/{group_openid}/files",
                group_openid=kwargs["group_openid"],
            )
            return await self.bot.api._http.request(route, json=payload)

    async def upload_group_and_c2c_record(
        self, 
        file_source: str, 
        file_type: int, 
        srv_send_msg: bool = False,
        **kwargs
    ) -> Optional[Media]:
        """
        上传媒体文件
        """
        # 构建基础payload
        payload = {
            "file_type": file_type,
            "srv_send_msg": srv_send_msg
        }
        
        # 处理文件数据
        if os.path.exists(file_source):
            # 读取本地文件
            async with aiofiles.open(file_source, 'rb') as f:
                file_content = await f.read()
                # use base64 encode
                payload["file_data"] = base64.b64encode(file_content).decode('utf-8')
        else:
            # 使用URL
            payload["url"] = file_source
        
        # 添加接收者信息和确定路由
        if "openid" in kwargs:
            payload["openid"] = kwargs["openid"]
            route = Route("POST", "/v2/users/{openid}/files", openid=kwargs["openid"])
        elif "group_openid" in kwargs:
            payload["group_openid"] =kwargs["group_openid"]
            route = Route("POST", "/v2/groups/{group_openid}/files", group_openid=kwargs["group_openid"])
        else:
            return None
        
        try:
            # 使用底层HTTP请求
            result = await self.bot.api._http.request(route, json=payload)
            
            if result:
                return Media(
                    file_uuid=result.get("file_uuid"),
                    file_info=result.get("file_info"),
                    ttl=result.get("ttl", 0),
                    file_id=result.get("id", "")
                )
        except Exception as e:
            logger.error(f"上传请求错误: {e}")
        
        return None
    
    async def post_c2c_message(
        self,
        openid: str,
        msg_type: int = 0,
        content: str = None,
        embed: message.Embed = None,
        ark: message.Ark = None,
        message_reference: message.Reference = None,
        media: message.Media = None,
        msg_id: str = None,
        msg_seq: str = 1,
        event_id: str = None,
        markdown: message.MarkdownPayload = None,
        keyboard: message.Keyboard = None,
        stream: dict = None,
    ) -> message.Message:
        payload = locals()
        payload.pop("self", None)
        route = Route("POST", "/v2/users/{openid}/messages", openid=openid)
        return await self.bot.api._http.request(route, json=payload)

    @staticmethod
    async def _parse_to_qqofficial(message: MessageChain):
        plain_text = ""
        image_base64 = None  # only one img supported
        image_file_path = None
        record_file_path = None
        for i in message.chain:
            if isinstance(i, Plain):
                plain_text += i.text
            elif isinstance(i, Image) and not image_base64:
                if i.file and i.file.startswith("file:///"):
                    image_base64 = file_to_base64(i.file[8:])
                    image_file_path = i.file[8:]
                elif i.file and i.file.startswith("http"):
                    image_file_path = await download_image_by_url(i.file)
                    image_base64 = file_to_base64(image_file_path)
                elif i.file and i.file.startswith("base64://"):
                    image_base64 = i.file
                else:
                    image_base64 = file_to_base64(i.file)
                image_base64 = image_base64.removeprefix("base64://")
            elif isinstance(i, Record):
                if i.file:
                    record_wav_path = await i.convert_to_file_path() # wav 路径
                    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                    record_tecent_silk_path = os.path.join(temp_dir, f"{uuid.uuid4()}.silk")
                    try:
                        duration = await wav_to_tencent_silk(record_wav_path, record_tecent_silk_path)
                        if duration > 0:
                            record_file_path = record_tecent_silk_path
                        else:
                            record_file_path = None                                 
                            logger.error("转换音频格式时出错：音频时长不大于0")
                    except Exception as e:
                        logger.error(f"处理语音时出错: {e}")
                        record_file_path = None                                     
            else:
                logger.debug(f"qq_official 忽略 {i.type}")
        return plain_text, image_base64, image_file_path, record_file_path
