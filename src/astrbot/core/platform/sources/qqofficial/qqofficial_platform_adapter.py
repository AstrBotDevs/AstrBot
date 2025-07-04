from __future__ import annotations

import botpy
import logging
import time
import asyncio
import botpy.message
import botpy.types
import botpy.types.message
import os

from botpy import Client
from astrbot.api.platform import (
    Platform,
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot import logger
from astrbot.api.event import MessageChain
from typing import Union, List
from astrbot.api.message_components import Image, Plain, At
from astrbot.core.platform.astr_message_event import MessageSesion
from .qqofficial_message_event import QQOfficialMessageEvent
from ...register import register_platform_adapter
from astrbot.core.message.components import BaseMessageComponent

# remove logger handler
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


# QQ 机器人官方框架
class botClient(Client):
    def set_platform(self, platform: "QQOfficialPlatformAdapter"):
        self.platform = platform

    # 收到群消息
    async def on_group_at_message_create(self, message: botpy.message.GroupMessage):
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message, MessageType.GROUP_MESSAGE
        )
        abm.session_id = (
            abm.sender.user_id if self.platform.unique_session else message.group_openid
        )
        self._commit(abm)

    # 收到频道消息
    async def on_at_message_create(self, message: botpy.message.Message):
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message, MessageType.GROUP_MESSAGE
        )
        abm.session_id = (
            abm.sender.user_id if self.platform.unique_session else message.channel_id
        )
        self._commit(abm)

    # 收到私聊消息
    async def on_direct_message_create(self, message: botpy.message.DirectMessage):
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message, MessageType.FRIEND_MESSAGE
        )
        abm.session_id = abm.sender.user_id
        self._commit(abm)

    # 收到 C2C 消息
    async def on_c2c_message_create(self, message: botpy.message.C2CMessage):
        abm = QQOfficialPlatformAdapter._parse_from_qqofficial(
            message, MessageType.FRIEND_MESSAGE
        )
        abm.session_id = abm.sender.user_id
        self._commit(abm)

    def _commit(self, abm: AstrBotMessage):
        self.platform.commit_event(
            QQOfficialMessageEvent(
                abm.message_str,
                abm,
                self.platform.meta(),
                abm.session_id,
                self.platform.client,
            )
        )


@register_platform_adapter("qq_official", "QQ 机器人官方 API 适配器")
class QQOfficialPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)

        self.config = platform_config

        self.appid = platform_config["appid"]
        self.secret = platform_config["secret"]
        self.unique_session = platform_settings["unique_session"]
        qq_group = platform_config["enable_group_c2c"]
        guild_dm = platform_config["enable_guild_direct_message"]

        if qq_group:
            self.intents = botpy.Intents(
                public_messages=True,
                public_guild_messages=True,
                direct_message=guild_dm,
            )
        else:
            self.intents = botpy.Intents(
                public_guild_messages=True, direct_message=guild_dm
            )
        self.client = botClient(
            intents=self.intents,
            bot_log=False,
            timeout=20,
        )

        self.client.set_platform(self)

        self.test_mode = os.environ.get("TEST_MODE", "off") == "on"

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        raise NotImplementedError("QQ 机器人官方 API 适配器不支持 send_by_session")

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="qq_official",
            description="QQ 机器人官方 API 适配器",
            id=self.config.get("id"),
        )

    @staticmethod
    def _parse_from_qqofficial(
        message: Union[botpy.message.Message, botpy.message.GroupMessage],
        message_type: MessageType,
    ):
        abm = AstrBotMessage()
        abm.type = message_type
        abm.timestamp = int(time.time())
        abm.raw_message = message
        abm.message_id = message.id
        abm.tag = "qq_official"
        msg: List[BaseMessageComponent] = []

        if isinstance(message, botpy.message.GroupMessage) or isinstance(
            message, botpy.message.C2CMessage
        ):
            if isinstance(message, botpy.message.GroupMessage):
                abm.sender = MessageMember(message.author.member_openid, "")
                abm.group_id = message.group_openid
            else:
                abm.sender = MessageMember(message.author.user_openid, "")
            abm.message_str = message.content.strip()
            abm.self_id = "unknown_selfid"
            msg.append(At(qq="qq_official"))
            msg.append(Plain(abm.message_str))
            if message.attachments:
                for i in message.attachments:
                    if i.content_type.startswith("image"):
                        url = i.url
                        if not url.startswith("http"):
                            url = "https://" + url
                        img = Image.fromURL(url)
                        msg.append(img)
            abm.message = msg

        elif isinstance(message, botpy.message.Message) or isinstance(
            message, botpy.message.DirectMessage
        ):
            try:
                abm.self_id = str(message.mentions[0].id)
            except BaseException as _:
                abm.self_id = ""

            plain_content = message.content.replace(
                "<@!" + str(abm.self_id) + ">", ""
            ).strip()

            if message.attachments:
                for i in message.attachments:
                    if i.content_type.startswith("image"):
                        url = i.url
                        if not url.startswith("http"):
                            url = "https://" + url
                        img = Image.fromURL(url)
                        msg.append(img)
            abm.message = msg
            abm.message_str = plain_content
            abm.sender = MessageMember(
                str(message.author.id), str(message.author.username)
            )
            msg.append(At(qq="qq_official"))
            msg.append(Plain(plain_content))

            if isinstance(message, botpy.message.Message):
                abm.group_id = message.channel_id
        else:
            raise ValueError(f"Unknown message type: {message_type}")
        abm.self_id = "qq_official"
        return abm

    def run(self):
        return self.client.start(appid=self.appid, secret=self.secret)

    def get_client(self) -> botClient:
        return self.client

    async def terminate(self):
        await self.client.close()
        logger.info("QQ 官方机器人接口 适配器已被优雅地关闭")
