import abc
from typing import Union
from nakuru import (
    GuildMessage,
    GroupMessage,
    FriendMessage,
)
from nakuru.entities.components import Plain, At, Image


class Platform():
    def __init__(self, message_handler: callable) -> None:
        '''
        初始化平台的各种接口
        '''
        self.message_handler = message_handler
        self.cnt_receive = 0
        self.cnt_reply = 0
        pass

    @abc.abstractmethod
    async def handle_msg(self):
        '''
        处理到来的消息
        '''
        self.cnt_receive += 1
        pass

    @abc.abstractmethod
    async def reply_msg(self):
        '''
        回复消息（被动发送）
        '''
        self.cnt_reply += 1
        pass

    @abc.abstractmethod
    async def send_msg(self, target: Union[GuildMessage, GroupMessage, FriendMessage, str], message: Union[str, list]):
        '''
        发送消息（主动发送）
        '''
        self.cnt_reply += 1
        pass

    @abc.abstractmethod
    async def send(self, target: Union[GuildMessage, GroupMessage, FriendMessage, str], message: Union[str, list]):
        '''
        发送消息（主动发送）同 send_msg()
        '''
        self.cnt_reply += 1
        pass

    def parse_message_outline(self, message: Union[GuildMessage, GroupMessage, FriendMessage, str, list]) -> str:
        '''
        将消息解析成大纲消息形式。
        如: xxxxx[图片]xxxxx
        '''
        if isinstance(message, str):
            return message
        ret = ''
        ls_to_parse = message if isinstance(message, list) else message.message
        try:
            for node in ls_to_parse:
                if isinstance(node, Plain):
                    ret += node.text
                elif isinstance(node, At):
                    ret += f'[At: {node.name}/{node.qq}]'
                elif isinstance(node, Image):
                    ret += '[图片]'
        except Exception as e:
            pass
        ret.replace('\n', '')
        return ret
