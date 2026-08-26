from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from . import HandlerFilter
from .command import CommandFilter
from .custom_filter import CustomFilter


# 指令组受配置的 command_prefixes framing 约束。
class CommandGroupFilter(HandlerFilter):
    def __init__(
        self,
        group_name: str,
        alias: set | None = None,
        parent_group: CommandGroupFilter | None = None,
    ) -> None:
        self.group_name = group_name
        self.alias = alias if alias else set()
        self._original_group_name = group_name
        self.sub_command_filters: list[CommandFilter | CommandGroupFilter] = []
        self.custom_filter_list: list[CustomFilter] = []
        self.parent_group = parent_group

        # Cache for complete command names list
        self._cmpl_cmd_names: list | None = None

    def add_sub_command_filter(
        self,
        sub_command_filter: CommandFilter | CommandGroupFilter,
    ) -> None:
        sub_command_filter.parent_group = self
        self.sub_command_filters.append(sub_command_filter)

    def add_custom_filter(self, custom_filter: CustomFilter) -> None:
        self.custom_filter_list.append(custom_filter)

    def format_invocation(
        self,
        command_name: str | None = None,
        include_aliases: bool = False,
    ) -> str:
        display_name = command_name or self.get_complete_command_names()[0]
        result = display_name
        if include_aliases and self.alias:
            aliases = ", ".join(sorted(self.alias))
            result += f" [aliases: {aliases}]"
        return result

    def get_complete_command_names(self) -> list[str]:
        """遍历父节点获取完整的指令名。

        新版本 v3.4.29 采用预编译指令，不再从指令组递归遍历子指令，因此这个方法是返回包括别名在内的整个指令名列表。
        """
        if self.parent_group is None and self._cmpl_cmd_names is not None:
            return self._cmpl_cmd_names

        parent_cmd_names = (
            self.parent_group.get_complete_command_names() if self.parent_group else []
        )

        if not parent_cmd_names:
            # 根节点
            self._cmpl_cmd_names = [self.group_name, *sorted(self.alias)]
            return self._cmpl_cmd_names

        result = []
        candidates = [self.group_name, *sorted(self.alias)]
        for parent_cmd_name in parent_cmd_names:
            for candidate in candidates:
                result.append(parent_cmd_name + " " + candidate)
        return result

    # 以树的形式打印出来
    def print_cmd_tree(
        self,
        sub_command_filters: list[CommandFilter | CommandGroupFilter],
        prefix: str = "",
        event: AstrMessageEvent | None = None,
        cfg: AstrBotConfig | None = None,
    ) -> str:
        parts = []
        for sub_filter in sub_command_filters:
            if isinstance(sub_filter, CommandFilter):
                custom_filter_pass = True
                if event and cfg:
                    custom_filter_pass = sub_filter.custom_filter_ok(event, cfg)
                if custom_filter_pass:
                    line = f"{prefix}├── {sub_filter.format_invocation(include_aliases=True)}"
                    if not sub_filter.print_types():
                        line += " (无参数指令)"

                    if sub_filter.handler_md and sub_filter.handler_md.desc:
                        line += f": {sub_filter.handler_md.desc}"

                    parts.append(line + "\n")
            elif isinstance(sub_filter, CommandGroupFilter):
                custom_filter_pass = True
                if event and cfg:
                    custom_filter_pass = sub_filter.custom_filter_ok(event, cfg)
                if custom_filter_pass:
                    parts.append(
                        f"{prefix}├── {sub_filter.format_invocation(include_aliases=True)}\n"
                    )
                    parts.append(
                        sub_filter.print_cmd_tree(
                            sub_filter.sub_command_filters,
                            prefix + "│   ",
                            event=event,
                            cfg=cfg,
                        )
                    )

        return "".join(parts)

    def custom_filter_ok(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        for custom_filter in self.custom_filter_list:
            if not custom_filter.filter(event, cfg):
                return False
        return True

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return False
