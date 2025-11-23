import inspect
import re
import types
import typing
from typing import Any

from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ..star_handler import StarHandlerMetadata
from . import HandlerFilter
from .custom_filter import CustomFilter


class GreedyStr(str):
    """标记指令完成其他参数接收后的所有剩余文本。"""


def unwrap_optional(annotation) -> tuple:
    """去掉 Optional[T] / Union[T, None] / T|None，返回 T"""
    args = typing.get_args(annotation)
    non_none_args = [a for a in args if a is not type(None)]
    if len(non_none_args) == 1:
        return (non_none_args[0],)
    if len(non_none_args) > 1:
        return tuple(non_none_args)
    return ()


# 标准指令受到 wake_prefix 的制约。
class CommandFilter(HandlerFilter):
    """标准指令过滤器"""

    def __init__(
        self,
        command_name: str,
        alias: set | None = None,
        handler_md: StarHandlerMetadata | None = None,
        parent_command_names: list[str] | None = None,
    ):
        self.command_name = command_name
        self.alias = alias if alias else set()
        self.parent_command_names = (
            parent_command_names if parent_command_names is not None else [""]
        )
        if handler_md:
            self.init_handler_md(handler_md)
        self.custom_filter_list: list[CustomFilter] = []

        # Cache for complete command names list
        self._cmpl_cmd_names: list | None = None

    def print_types(self):
        parts = []
        for k, v in self.handler_params.items():
            if isinstance(v, type):
                parts.append(f"{k}({v.__name__}),")
            elif isinstance(v, types.UnionType) or typing.get_origin(v) is typing.Union:
                parts.append(f"{k}({v}),")
            else:
                parts.append(f"{k}({type(v).__name__})={v},")
        result = "".join(parts).rstrip(",")
        return result

    def init_handler_md(self, handle_md: StarHandlerMetadata):
        self.handler_md = handle_md
        signature = inspect.signature(self.handler_md.handler)
        self.handler_params = {}  # 参数名 -> 参数类型，如果有默认值则为默认值
        idx = 0
        for k, v in signature.parameters.items():
            if idx < 2:
                # 忽略前两个参数，即 self 和 event
                idx += 1
                continue
            if v.default == inspect.Parameter.empty:
                self.handler_params[k] = v.annotation
            else:
                self.handler_params[k] = v.default

    def get_handler_md(self) -> StarHandlerMetadata:
        return self.handler_md

    def add_custom_filter(self, custom_filter: CustomFilter):
        self.custom_filter_list.append(custom_filter)

    def custom_filter_ok(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        for custom_filter in self.custom_filter_list:
            if not custom_filter.filter(event, cfg):
                return False
        return True

    def validate_and_convert_params(
        self,
        params: list[Any],
        param_type: dict[str, type],
    ) -> dict[str, Any]:
        """将参数列表 params 根据 param_type 转换为参数字典。"""
        result = {}
        param_items = list(param_type.items())
        for i, (param_name, param_type_or_default_val) in enumerate(param_items):
            is_greedy = param_type_or_default_val is GreedyStr

            if is_greedy:
                # GreedyStr 必须是最后一个参数
                if i != len(param_items) - 1:
                    raise ValueError(
                        f"参数 '{param_name}' (GreedyStr) 必须是最后一个参数。",
                    )

                # 将剩余的所有部分合并成一个字符串
                remaining_params = params[i:]
                result[param_name] = " ".join(remaining_params)
                break
            # 没有 GreedyStr 的情况
            if i >= len(params):
                if (
                    isinstance(param_type_or_default_val, (type, types.UnionType))
                    or typing.get_origin(param_type_or_default_val) is typing.Union
                    or param_type_or_default_val is inspect.Parameter.empty
                ):
                    # 是类型
                    raise ValueError(
                        f"必要参数缺失。该指令完整参数: {self.print_types()}",
                    )
                # 是默认值
                result[param_name] = param_type_or_default_val
            else:
                # 尝试强制转换
                try:
                    if param_type_or_default_val is None:
                        if params[i].isdigit():
                            result[param_name] = int(params[i])
                        else:
                            result[param_name] = params[i]
                    elif isinstance(param_type_or_default_val, str):
                        # 如果 param_type_or_default_val 是字符串，直接赋值
                        result[param_name] = params[i]
                    elif isinstance(param_type_or_default_val, bool):
                        # 处理布尔类型
                        lower_param = str(params[i]).lower()
                        if lower_param in ["true", "yes", "1"]:
                            result[param_name] = True
                        elif lower_param in ["false", "no", "0"]:
                            result[param_name] = False
                        else:
                            raise ValueError(
                                f"参数 {param_name} 必须是布尔值（true/false, yes/no, 1/0）。",
                            )
                    elif isinstance(param_type_or_default_val, int):
                        result[param_name] = int(params[i])
                    elif isinstance(param_type_or_default_val, float):
                        result[param_name] = float(params[i])
                    else:
                        origin = typing.get_origin(param_type_or_default_val)
                        if origin in (typing.Union, types.UnionType):
                            # 注解是联合类型
                            # NOTE: 目前没有处理联合类型嵌套相关的注解写法
                            nn_types = unwrap_optional(param_type_or_default_val)
                            if len(nn_types) == 1:
                                # 只有一个非 NoneType 类型
                                result[param_name] = nn_types[0](params[i])
                            else:
                                # 没有或者有多个非 NoneType 类型，这里我们暂时直接赋值为原始值。
                                # NOTE: 目前还没有做类型校验
                                result[param_name] = params[i]
                        else:
                            result[param_name] = param_type_or_default_val(params[i])
                except ValueError:
                    raise ValueError(
                        f"参数 {param_name} 类型错误。完整参数: {self.print_types()}",
                    )
        return result

    def get_complete_command_names(self):
        if self._cmpl_cmd_names is not None:
            return self._cmpl_cmd_names
        self._cmpl_cmd_names = [
            f"{parent} {cmd}" if parent else cmd
            for cmd in [self.command_name] + list(self.alias)
            for parent in self.parent_command_names or [""]
        ]
        return self._cmpl_cmd_names

    def equals(self, message_str: str) -> bool:
        for full_cmd in self.get_complete_command_names():
            if message_str == full_cmd:
                return True
        return False

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        if not event.is_at_or_wake_command:
            return False

        if not self.custom_filter_ok(event, cfg):
            return False

        # 检查是否以指令开头
        message_str = re.sub(r"\s+", " ", event.get_message_str().strip())
        ok = False
        for full_cmd in self.get_complete_command_names():
            if message_str.startswith(f"{full_cmd} ") or message_str == full_cmd:
                ok = True
                message_str = message_str[len(full_cmd) :].strip()
        if not ok:
            return False

        # 分割为列表
        ls = message_str.split(" ")
        # 去除空字符串
        ls = [param for param in ls if param]
        params = {}
        try:
            params = self.validate_and_convert_params(ls, self.handler_params)
        except ValueError as e:
            raise e

        event.set_extra("parsed_params", params)

        return True
