from typing import List, Union, Optional
from dataclasses import dataclass
from type.register import RegisteredPlatform
from type.types import Context
from type.astrbot_message import AstrBotMessage

class AstrMessageEvent():

    def __init__(self,
                 message_str: str,
                 message_obj: AstrBotMessage,
                 platform: RegisteredPlatform,
                 role: str,
                 context: Context,
                 session_id: str = None):
        '''
        AstrBot 消息事件。
        
        `message_str`: 纯消息字符串
        `message_obj`: AstrBotMessage 对象
        `platform`: 平台对象
        `role`: 角色，`admin` or `member`
        `context`: 全局对象
        `session_id`: 会话id
        '''
        self.context = context
        self.message_str = message_str
        self.message_obj = message_obj
        self.platform = platform
        self.role = role
        self.session_id = session_id
        
    def from_astrbot_message(message: AstrBotMessage, 
                             context: Context,
                             platform_name: str, 
                             session_id: str,
                             role: str = "member"):
        
        ame = AstrMessageEvent(message.message_str, 
                               message, 
                               context.find_platform(platform_name), 
                               role, 
                               context, 
                               session_id)
        return ame

@dataclass
class MessageResult():
    result_message: Union[str, list]
    is_command_call: Optional[bool] = False
    use_t2i: Optional[bool] = None # None 为跟随用户设置
    callback: Optional[callable] = None
