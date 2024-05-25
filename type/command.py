from typing import Union, List, Callable
from dataclasses import dataclass


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

    def __init__(self, hit: bool, success: bool = False, message_chain: list = [], command_name: str = "unknown_command") -> None:
        self.hit = hit
        self.success = success
        self.message_chain = message_chain
        self.command_name = command_name

    def _result_tuple(self):
        return (self.success, self.message_chain, self.command_name)
