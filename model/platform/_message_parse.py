from nakuru.entities.components import Plain, At, Image, BaseMessageComponent
from nakuru import (
    GuildMessage,
    GroupMessage,
    FriendMessage
)
import botpy.message
from cores.astrbot.types import MessageType, AstrBotMessage, MessageMember
from typing import List, Union
import time

# QQ官方消息类型转换


def qq_official_message_parse(message: List[BaseMessageComponent]):
    plain_text = ""
    image_path = None  # only one img supported
    for i in message:
        if isinstance(i, Plain):
            plain_text += i.text
        elif isinstance(i, Image) and image_path == None:
            if i.path is not None:
                image_path = i.path
            else:
                image_path = i.file
    return plain_text, image_path

# QQ官方消息类型 2 AstrBotMessage


def qq_official_message_parse_rev(message: Union[botpy.message.Message, botpy.message.GroupMessage],
                                  message_type: MessageType) -> AstrBotMessage:
    abm = AstrBotMessage()
    abm.type = message_type
    abm.timestamp = int(time.time())
    abm.raw_message = message
    abm.message_id = message.id
    abm.tag = "qqchan"
    msg: List[BaseMessageComponent] = []

    if message_type == MessageType.GROUP_MESSAGE:
        abm.sender = MessageMember(
            message.author.member_openid,
            ""
        )
        abm.message_str = message.content.strip()
        abm.self_id = "unknown_selfid"

        msg.append(Plain(abm.message_str))
        if message.attachments:
            for i in message.attachments:
                if i.content_type.startswith("image"):
                    url = i.url
                    if not url.startswith("http"):
                        url = "https://"+url
                    img = Image.fromURL(url)
                    msg.append(img)
        abm.message = msg

    elif message_type == MessageType.GUILD_MESSAGE or message_type == MessageType.FRIEND_MESSAGE:
        # 目前对于 FRIEND_MESSAGE 只处理频道私聊
        try:
            abm.self_id = str(message.mentions[0].id)
        except:
            abm.self_id = ""

        plain_content = message.content.replace(
            "<@!"+str(abm.self_id)+">", "").strip()
        msg.append(Plain(plain_content))
        if message.attachments:
            for i in message.attachments:
                if i.content_type.startswith("image"):
                    url = i.url
                    if not url.startswith("http"):
                        url = "https://"+url
                    img = Image.fromURL(url)
                    msg.append(img)
        abm.message = msg
        abm.message_str = plain_content
        abm.sender = MessageMember(
            str(message.author.id),
            str(message.author.username)
        )
    else:
        raise ValueError(f"Unknown message type: {message_type}")
    return abm


def nakuru_message_parse_rev(message: Union[GuildMessage, GroupMessage, FriendMessage]) -> AstrBotMessage:
    abm = AstrBotMessage()
    abm.type = MessageType(message.type)
    abm.timestamp = int(time.time())
    abm.raw_message = message
    abm.message_id = message.message_id

    plain_content = ""
    for i in message.message:
        if isinstance(i, Plain):
            plain_content += i.text
    abm.message_str = plain_content

    abm.self_id = str(message.self_id)
    abm.sender = MessageMember(
        str(message.sender.user_id),
        str(message.sender.nickname)
    )
    abm.tag = "gocq"
    abm.message = message.message

    return abm
