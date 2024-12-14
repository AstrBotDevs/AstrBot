from __future__ import annotations

import re
from typing import List, Union, Tuple
from . import HandlerFilter
from .command import CommandFilter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig
from ..star_handler import StarHandlerMetadata

# 指令组受到 wake_prefix 的制约。
class CommandGroupFilter(HandlerFilter):
    def __init__(self, group_name: str):
        self.group_name = group_name
        self.sub_command_filters: List[Union[CommandFilter, CommandGroupFilter]] = []
    
    def add_sub_command_filter(self, sub_command_filter: Union[CommandFilter, CommandGroupFilter]):
        self.sub_command_filters.append(sub_command_filter)
    
    # 以树的形式打印出来
    def print_cmd_tree(self, sub_command_filters: List[Union[CommandFilter, CommandGroupFilter]], prefix: str = "") -> str:
        result = ""
        for sub_filter in sub_command_filters:
            if isinstance(sub_filter, CommandFilter):
                cmd_th = sub_filter.print_types()
                result += f"{prefix}├── {sub_filter.command_name}"
                if cmd_th:
                    result += f" ({cmd_th})"
                else:
                    result += " (无参数指令)"
                
                result += "\n"
            elif isinstance(sub_filter, CommandGroupFilter):
                result += f"{prefix}├── {sub_filter.group_name}"
                result += "\n"
                result += sub_filter.print_cmd_tree(sub_filter.sub_command_filters, prefix+"│   ")
        return result
        
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> Tuple[bool, StarHandlerMetadata]:
        if not event.is_wake_up():
            return False, None
        
        message_str = event.get_message_str().strip()
        ls = re.split(r"\s+", message_str)
        
        if ls[0] != self.group_name:
            return False, None
        # 改写 message_str
        ls = ls[1:]
        event.message_str = " ".join(ls)
        event.message_str = event.message_str.strip()
        
        if event.message_str == "":
            # 当前还是指令组
            tree = self.group_name + "\n" + self.print_cmd_tree(self.sub_command_filters)
            raise ValueError(f"指令组 {self.group_name} 未填写完全。这个指令组下有如下指令：\n"+tree)
        
        child_command_handler_md = None
        for sub_filter in self.sub_command_filters:
            if isinstance(sub_filter, CommandFilter):
                if sub_filter.filter(event, cfg):
                    child_command_handler_md = sub_filter.get_handler_md()
                    return True, child_command_handler_md
            elif isinstance(sub_filter, CommandGroupFilter):
                ok, handler = sub_filter.filter(event, cfg)
                if ok:
                    child_command_handler_md = handler
                    return True, child_command_handler_md
        tree = self.group_name + "\n" + self.print_cmd_tree(self.sub_command_filters)
        raise ValueError(f"指令组 {self.group_name} 下没有找到对应的指令。这个指令组下有如下指令：\n"+tree)
