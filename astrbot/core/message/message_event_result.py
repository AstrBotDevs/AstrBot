from typing import List, Union, Optional
from dataclasses import dataclass, field
from astrbot.core.message.components import *

@dataclass
class MessageChain():
    chain: List[BaseMessageComponent] = field(default_factory=list)
    use_t2i_: Optional[bool] = None # None 为跟随用户设置
    is_split_: Optional[bool] = False # 是否将消息分条发送。默认为 False。启用后，将会依次发送 chain 中的每个 component。
    
    def message(self, message: str):
        '''
        快捷回复消息。
        
        CommandResult().message("Hello, world!")
        '''
        self.chain.append(Plain(message))
        return self
    
    def error(self, message: str):
        '''
        快捷回复消息。
        
        CommandResult().error("Hello, world!")
        '''
        self.chain.append(Plain(message))
        return self
    
    def url_image(self, url: str):
        '''
        快捷回复图片(网络url的格式)。
        
        CommandResult().image("https://example.com/image.jpg")
        '''
        self.chain.append(Image.fromURL(url))
        return self
    
    def file_image(self, path: str):
        '''
        快捷回复图片(本地文件路径的格式)。
        
        CommandResult().image("image.jpg")
        '''
        self.chain.append(Image.fromFileSystem(path))
        return self
    
    def use_t2i(self, use_t2i: bool):
        '''
        设置是否使用文本转图片服务。如果不设置，则跟随用户的设置。
        '''
        self.use_t2i_ = use_t2i
        return self
    
    def is_split(self, is_split: bool):
        '''
        设置是否分条发送消息。默认为 False。启用后，将会依次发送 chain 中的每个 component。
        
        具体的效果以各适配器实现为准。
        '''
        self.is_split_ = is_split
        return self

@dataclass
class MessageEventResult(MessageChain):
    is_command_call: Optional[bool] = False
    callback: Optional[callable] = None
    
CommandResult = MessageEventResult