from __future__ import annotations

import re
from typing import List, Union, Tuple
from . import HandlerFilter
from .command import CommandFilter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig
from .custom_filter import CustomFilter
from ..star_handler import StarHandlerMetadata

# 指令组受到 wake_prefix 的制约。
class CommandGroupFilter(HandlerFilter):
    def __init__(self, group_name: str, alias: set = None):
        self.group_name = group_name
        self.alias = alias if alias else set()
        self.sub_command_filters: List[Union[CommandFilter, CommandGroupFilter]] = []
        self.custom_filter_list: List[CustomFilter] = []
    
    def add_sub_command_filter(self, sub_command_filter: Union[CommandFilter, CommandGroupFilter]):
        self.sub_command_filters.append(sub_command_filter)

    def add_custom_filter(self, custom_filter: CustomFilter):
        self.custom_filter_list.append(custom_filter)

    # 以树的形式打印出来
    def print_cmd_tree(self,
        sub_command_filters: List[Union[CommandFilter, CommandGroupFilter]],
        prefix: str = "",
        event: AstrMessageEvent = None,
        cfg: AstrBotConfig = None,
    ) -> str:
        result = ""
        for sub_filter in sub_command_filters:
            if isinstance(sub_filter, CommandFilter):
                custom_filter_pass = True
                if event and cfg:
                    custom_filter_pass = sub_filter.custom_filter_ok(event, cfg)
                if custom_filter_pass:
                    cmd_th = sub_filter.print_types()
                    result += f"{prefix}├── {sub_filter.command_name}"
                    if cmd_th:
                        result += f" ({cmd_th})"
                    else:
                        result += " (无参数指令)"
                    result += "\n"
            elif isinstance(sub_filter, CommandGroupFilter):
                custom_filter_pass = True
                if event and cfg:
                    custom_filter_pass = sub_filter.custom_filter_ok(event, cfg)
                if custom_filter_pass:
                    result += f"{prefix}├── {sub_filter.group_name}"
                    result += "\n"
                    result += sub_filter.print_cmd_tree(sub_filter.sub_command_filters, prefix+"│   ", event=event, cfg=cfg)

        return result

    def custom_filter_ok(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        for custom_filter in self.custom_filter_list:
            if not custom_filter.filter(event, cfg):
                return False
        return True

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> Tuple[bool, StarHandlerMetadata]:
        if not event.is_at_or_wake_command:
            return False, None
        
        if event.get_extra("parsing_command"):
            message_str = event.get_extra("parsing_command").strip()
        else:
            message_str = event.get_message_str().strip()
        
        ls = re.split(r"\s+", message_str)

        if ls[0] != self.group_name and ls[0] not in self.alias:
            return False, None
        # 改写 message_str
        ls = ls[1:]
        # event.message_str = " ".join(ls)
        # event.message_str = event.message_str.strip()
        parsing_command = " ".join(ls)
        parsing_command = parsing_command.strip()
        event.set_extra("parsing_command", parsing_command)

        # 判断当前指令组的自定义过滤器
        if not self.custom_filter_ok(event, cfg):
            return False, None

        if parsing_command == "":
            # 当前还是指令组
            tree = self.group_name + "\n" + self.print_cmd_tree(self.sub_command_filters, event=event, cfg=cfg)
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
        tree = self.group_name + "\n" + self.print_cmd_tree(self.sub_command_filters, event=event, cfg=cfg)
        raise ValueError(f"指令组 {self.group_name} 下没有找到对应的指令。这个指令组下有如下指令：\n"+tree)
