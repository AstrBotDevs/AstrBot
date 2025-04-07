from __future__ import annotations

from typing import List, Union
from . import HandlerFilter
from .command import CommandFilter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig
from .custom_filter import CustomFilter


# 指令组受到 wake_prefix 的制约。
class CommandGroupFilter(HandlerFilter):
    def __init__(
        self,
        group_name: str,
        alias: set = None,
        parent_group: CommandGroupFilter = None,
    ):
        self.group_name = group_name
        self.alias = alias if alias else set()
        self.sub_command_filters: List[Union[CommandFilter, CommandGroupFilter]] = []
        self.custom_filter_list: List[CustomFilter] = []
        self.parent_group = parent_group

    def add_sub_command_filter(
        self, sub_command_filter: Union[CommandFilter, CommandGroupFilter]
    ):
        self.sub_command_filters.append(sub_command_filter)

    def add_custom_filter(self, custom_filter: CustomFilter):
        self.custom_filter_list.append(custom_filter)

    def get_complete_command_names(self) -> List[str]:
        """遍历父节点获取完整的指令名。

        新版本 v3.4.29 采用预编译指令，不再从指令组递归遍历子指令，因此这个方法是返回包括别名在内的整个指令名列表。"""
        parent_cmd_names = (
            self.parent_group.get_complete_command_names() if self.parent_group else []
        )

        if not parent_cmd_names:
            # 根节点
            return [self.group_name] + list(self.alias)

        result = []
        candidates = [self.group_name] + list(self.alias)
        for parent_cmd_name in parent_cmd_names:
            for candidate in candidates:
                result.append(parent_cmd_name + " " + candidate)
        return result

    # 以树的形式打印出来
    def print_cmd_tree(
        self,
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

                    if sub_filter.handler_md and sub_filter.handler_md.desc:
                        result += f": {sub_filter.handler_md.desc}"

                    result += "\n"
            elif isinstance(sub_filter, CommandGroupFilter):
                custom_filter_pass = True
                if event and cfg:
                    custom_filter_pass = sub_filter.custom_filter_ok(event, cfg)
                if custom_filter_pass:
                    result += f"{prefix}├── {sub_filter.group_name}"
                    result += "\n"
                    result += sub_filter.print_cmd_tree(
                        sub_filter.sub_command_filters,
                        prefix + "│   ",
                        event=event,
                        cfg=cfg,
                    )

        return result

    def custom_filter_ok(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        for custom_filter in self.custom_filter_list:
            if not custom_filter.filter(event, cfg):
                return False
        return True

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        if not event.is_at_or_wake_command:
            return False

        # 判断当前指令组的自定义过滤器
        if not self.custom_filter_ok(event, cfg):
            return False

        complete_command_names = self.get_complete_command_names()
        if event.message_str.strip() in complete_command_names:
            tree = (
                self.group_name
                + "\n"
                + self.print_cmd_tree(self.sub_command_filters, event=event, cfg=cfg)
            )
            raise ValueError(
                f"指令组 {self.group_name} 未填写完全。这个指令组下有如下指令：\n"
                + tree
            )

        # complete_command_names = [name + " " for name in complete_command_names]
        # return event.message_str.startswith(tuple(complete_command_names))
        return False
