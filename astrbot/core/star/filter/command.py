
import re, inspect
from . import HandlerFilter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig
from astrbot.core.utils.param_validation_mixin import ParameterValidationMixin
from typing import Awaitable
from ..star_handler import StarHandlerMetadata

# 标准指令受到 wake_prefix 的制约。
class CommandFilter(HandlerFilter, ParameterValidationMixin):
    '''标准指令过滤器'''
    def __init__(self, command_name: str, handler_md: StarHandlerMetadata = None):
        self.command_name = command_name
        if handler_md:
            self.init_handler_md(handler_md)
            
    def print_types(self):
        result = ""
        print(self.handler_params)
        for k, v in self.handler_params.items():
            if isinstance(v, type):
                result += f"{k}({v.__name__}),"
            else:
                result += f"{k}({type(v).__name__})={v},"
        return result
                
    def init_handler_md(self, handle_md: StarHandlerMetadata):
        self.handler_md = handle_md
        signature = inspect.signature(self.handler_md.handler)
        self.handler_params = {} # 参数名 -> 参数类型，如果有默认值则为默认值
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

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        if not event.is_wake_up():
            return False
        
        message_str = event.get_message_str().strip()
        # 分割为列表（每个参数之间可能会有多个空格）
        ls = re.split(r"\s+", message_str)
        if self.command_name != ls[0]:
            return False
        # params_str = message_str[len(self.command_name):].strip()
        ls = ls[1:]
        # 去除空字符串
        ls = [param for param in ls if param]
        params = {}
        try:
            params = self.validate_and_convert_params(ls, self.handler_params)
            # 解析完成咱也不能丢掉呀，留着给后面的用
        except ValueError as e:
            raise e
        event.set_extra("parsed_params", params)
        
        return True