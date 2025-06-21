import re
import inspect
from typing import List, Any, Type, Dict
from . import HandlerFilter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig
from .custom_filter import CustomFilter
from ..star_handler import StarHandlerMetadata

class GreedyStr(str):
    """标记指令完成其他参数接收后的所有剩余文本。"""
    pass

# 标准指令受到 wake_prefix 的制约。
class CommandFilter(HandlerFilter):
    """标准指令过滤器"""

    def __init__(
        self,
        command_name: str,
        alias: set = None,
        handler_md: StarHandlerMetadata = None,
        parent_command_names: List[str] = [""],
    ):
        self.command_name = command_name
        self.alias = alias if alias else set()
        self.parent_command_names = parent_command_names
        if handler_md:
            self.init_handler_md(handler_md)
        self.custom_filter_list: List[CustomFilter] = []

    def print_types(self):
        result = ""
        for k, v in self.handler_params.items():
            if isinstance(v, type):
                result += f"{k}({v.__name__}),"
            else:
                result += f"{k}({type(v).__name__})={v},"
        result = result.rstrip(",")
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
        self, params: List[Any], param_type: Dict[str, Type]
    ) -> Dict[str, Any]:
        """将参数列表 params 根据 param_type 转换为参数字典。"""
        result = {}
        param_items = list(param_type.items())
        for i, (param_name, param_type_or_default_val) in enumerate(param_items):
            is_greedy = param_type_or_default_val is GreedyStr

            if is_greedy:
                # GreedyStr 必须是最后一个参数
                if i != len(param_items) - 1:
                    raise ValueError(
                        f"参数 '{param_name}' (GreedyStr) 必须是最后一个参数。"
                    )

                # 将剩余的所有部分合并成一个字符串
                remaining_params = params[i:]
                result[param_name] = " ".join(remaining_params)
                break
            # 没有 GreedyStr 的情况
            if i >= len(params):
                if (
                    isinstance(param_type_or_default_val, Type)
                    or param_type_or_default_val is inspect.Parameter.empty
                ):
                    # 是类型
                    raise ValueError(
                        f"必要参数缺失。该指令完整参数: {self.print_types()}"
                    )
                else:
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
                    elif isinstance(param_type_or_default_val, int):
                        result[param_name] = int(params[i])
                    elif isinstance(param_type_or_default_val, float):
                        result[param_name] = float(params[i])
                    else:
                        result[param_name] = param_type_or_default_val(params[i])
                except ValueError:
                    raise ValueError(
                        f"参数 {param_name} 类型错误。完整参数: {self.print_types()}"
                    )
        return result

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        if not event.is_at_or_wake_command:
            return False

        if not self.custom_filter_ok(event, cfg):
            return False

        # 检查是否以指令开头
        message_str = re.sub(r"\s+", " ", event.get_message_str().strip())
        candidates = [self.command_name] + list(self.alias)
        ok = False
        for candidate in candidates:
            for parent_command_name in self.parent_command_names:
                if parent_command_name:
                    _full = f"{parent_command_name} {candidate}"
                else:
                    _full = candidate
                if message_str.startswith(f"{_full} ") or message_str == _full:
                    message_str = message_str[len(_full) :].strip()
                    ok = True
                    break
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
