import abc
import threading
import asyncio
from typing import Callable, Union
from nakuru import (
    GuildMessage,
    GroupMessage,
    FriendMessage,
)
from ._nakuru_translation_layer import (
    NakuruGuildMessage,
)
from nakuru.entities.components import Plain, At, Image


class Platform():
    def __init__(self, message_handler: callable) -> None:
        '''
        初始化平台的各种接口
        '''
        self.message_handler = message_handler
        pass

    @abc.abstractmethod
    def handle_msg():
        '''
        处理到来的消息
        '''
        pass

    @abc.abstractmethod
    def reply_msg():
        '''
        回复消息（被动发送）
        '''
        pass

    @abc.abstractmethod
    def send_msg():
        '''
        发送消息（主动发送）
        '''
        pass

    @abc.abstractmethod
    def send():
        '''
        发送消息（主动发送）同 send_msg()
        '''
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


    def new_sub_thread(self, func, args=()):
        thread = threading.Thread(target=self._runner, args=(func, args), daemon=True)
        thread.start()

    def _runner(self, func: Callable, args: tuple):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(func(*args))
        loop.close()
