import botpy
import botpy.message
import botpy.types
import botpy.types.message
from astrbot.core.utils.io import file_to_base64, download_image_by_url
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image
from botpy import Client
from botpy.http import Route
from astrbot.api import logger


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
        if not self.send_buffer:
            self.send_buffer = message
        else:
            self.send_buffer.chain.extend(message.chain)

    async def _post_send(self):
        """QQ 官方 API 仅支持回复一次"""
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
        ) = await QQOfficialMessageEvent._parse_to_qqofficial(self.send_buffer)

        if not plain_text and not image_base64 and not image_path:
            return

        payload = {
            "content": plain_text,
            "msg_id": self.message_obj.message_id,
        }

        match type(source):
            case botpy.message.GroupMessage:
                if image_base64:
                    media = await self.upload_group_and_c2c_image(
                        image_base64, 1, group_openid=source.group_openid
                    )
                    payload["media"] = media
                    payload["msg_type"] = 7
                await self.bot.api.post_group_message(
                    group_openid=source.group_openid, **payload
                )
            case botpy.message.C2CMessage:
                if image_base64:
                    media = await self.upload_group_and_c2c_image(
                        image_base64, 1, openid=source.author.user_openid
                    )
                    payload["media"] = media
                    payload["msg_type"] = 7
                await self.bot.api.post_c2c_message(
                    openid=source.author.user_openid, **payload
                )
            case botpy.message.Message:
                if image_path:
                    payload["file_image"] = image_path
                await self.bot.api.post_message(channel_id=source.channel_id, **payload)
            case botpy.message.DirectMessage:
                if image_path:
                    payload["file_image"] = image_path
                await self.bot.api.post_dms(guild_id=source.guild_id, **payload)

        await super().send(self.send_buffer)

        self.send_buffer = None

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

    @staticmethod
    async def _parse_to_qqofficial(message: MessageChain):
        plain_text = ""
        image_base64 = None  # only one img supported
        image_file_path = None
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
            else:
                logger.debug(f"qq_official 忽略 {i.type}")
        return plain_text, image_base64, image_file_path
