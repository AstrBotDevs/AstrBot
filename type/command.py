from typing import Union, List, Callable
from dataclasses import dataclass
from nakuru.entities.components import Plain, Image


@dataclass
class CommandItem():
    '''
    用来描述单个指令
    '''

    command_name: Union[str, tuple]  # 指令名
    callback: Callable  # 回调函数
    description: str  # 描述
    origin: str  # 注册来源

class CommandResult():
    '''
    用于在Command中返回多个值
    '''

    def __init__(self, hit: bool = True, success: bool = True, message_chain: list = [], command_name: str = "unknown_command") -> None:
        self.hit = hit
        self.success = success
        self.message_chain = message_chain
        self.command_name = command_name
        
    def message(self, message: str):
        '''
        快捷回复消息。
        
        CommandResult().message("Hello, world!")
        '''
        self.message_chain = [Plain(message), ]
        return self
    
    def error(self, message: str):
        '''
        快捷回复消息。
        
        CommandResult().error("Hello, world!")
        '''
        self.success = False
        self.message_chain = [Plain(message), ]
        return self
    
    def url_image(self, url: str):
        '''
        快捷回复图片(网络url的格式)。
        
        CommandResult().image("https://example.com/image.jpg")
        '''
        self.message_chain = [Image.fromURL(url), ]
        return self
    
    def file_image(self, path: str):
        '''
        快捷回复图片(本地文件路径的格式)。
        
        CommandResult().image("image.jpg")
        '''
        self.message_chain = [Image.fromFileSystem(path), ]
        return self

    def _result_tuple(self):
        return (self.success, self.message_chain, self.command_name)
