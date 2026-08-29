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
    ) -> None:
        self.command_name = command_name
        self.alias = alias if alias else set()
        self._original_command_name = command_name
        self.parent_command_names = (
            parent_command_names if parent_command_names is not None else [""]
        )
        # Default values of handler parameters, used when the user omits them
        self.handler_param_defaults: dict[str, Any] = {}
        if handler_md:
            self.init_handler_md(handler_md)
        self.custom_filter_list: list[CustomFilter] = []

        # Cache for complete command names list
        self._cmpl_cmd_names: list | None = None

    def print_types(self):
        """Render the handler parameter list in a human-readable form for error hints."""
        parts = []
        for k, v in self.handler_params.items():
            default = self.handler_param_defaults.get(k, inspect.Parameter.empty)
            if isinstance(v, type):
                label = v.__name__
            elif isinstance(v, types.UnionType) or typing.get_origin(v) is typing.Union:
                label = str(v)
            elif v is inspect.Parameter.empty:
                label = "any"
            else:
                label = type(v).__name__
            if default is inspect.Parameter.empty:
                parts.append(f"{k}({label}),")
            else:
                parts.append(f"{k}({label})={default},")
        return "".join(parts).rstrip(",")

    def init_handler_md(self, handle_md: StarHandlerMetadata) -> None:
        self.handler_md = handle_md
        signature = inspect.signature(self.handler_md.handler, eval_str=True)
        # 参数名 -> 类型注解（无注解时回退为默认值或空标记）
        self.handler_params = {}
        # 参数名 -> 默认值（仅当参数有默认值时）
        self.handler_param_defaults = {}
        idx = 0
        for k, v in signature.parameters.items():
            if idx < 2:
                # 忽略前两个参数，即 self 和 event
                idx += 1
                continue
            if v.annotation is not inspect.Parameter.empty:
                # 优先使用类型注解作为参数转换的目标类型
                self.handler_params[k] = v.annotation
            elif v.default is not inspect.Parameter.empty and v.default is not None:
                # 无注解时，用默认值的运行时类型推断转换目标，保持旧行为
                self.handler_params[k] = v.default
            else:
                # 无注解且无默认值（或默认值为 None）：运行时按启发式处理
                self.handler_params[k] = inspect.Parameter.empty
            if v.default is not inspect.Parameter.empty:
                self.handler_param_defaults[k] = v.default

    def get_handler_md(self) -> StarHandlerMetadata:
        return self.handler_md

    def add_custom_filter(self, custom_filter: CustomFilter) -> None:
        self.custom_filter_list.append(custom_filter)

    def custom_filter_ok(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        for custom_filter in self.custom_filter_list:
            if not custom_filter.filter(event, cfg):
                return False
        return True

    def _convert_param(self, param_name: str, raw_value: str, target: Any) -> Any:
        """Convert a single raw string parameter according to its target type.

        The target type is normally the declared annotation. When there is no
        annotation, the target falls back to the runtime type of the default
        value, or to an empty marker that keeps the legacy heuristic.

        Args:
            param_name: Parameter name, used in error hints.
            raw_value: Raw string value provided by the user.
            target: Type annotation, or a default value / empty marker when
                the parameter has no annotation.

        Returns:
            The converted parameter value.

        Raises:
            ValueError: When the raw value cannot be converted to the target.
        """
        try:
            if (
                target is None
                or target is inspect.Parameter.empty
                or target is typing.Any
            ):
                # No type constraint: keep the legacy heuristic that parses
                # digit strings as int.
                return int(raw_value) if raw_value.isdigit() else raw_value
            origin = typing.get_origin(target)
            if origin in (typing.Union, types.UnionType):
                # Union annotation: when only one non-None type remains after
                # unwrapping Optional, convert to it; otherwise keep the raw
                # value (no type validation for multi-type unions yet).
                non_none_types = unwrap_optional(target)
                if len(non_none_types) == 1:
                    return self._convert_param(param_name, raw_value, non_none_types[0])
                return raw_value
            if target is str:
                # str is the raw value itself, no conversion needed
                return raw_value
            if target is bool:
                # Accept true/false, yes/no, 1/0
                lower_value = str(raw_value).lower()
                if lower_value in ("true", "yes", "1"):
                    return True
                if lower_value in ("false", "no", "0"):
                    return False
                raise ValueError(
                    f"参数 {param_name} 必须是布尔值（true/false, yes/no, 1/0）。",
                )
            if isinstance(target, type):
                # Plain type: convert via its constructor (int/float/custom)
                return target(raw_value)
            # No annotation: infer the target from the default value type
            if isinstance(target, bool):
                # bool first since it is a subclass of int
                return self._convert_param(param_name, raw_value, bool)
            if isinstance(target, str):
                return raw_value
            if isinstance(target, int):
                return int(raw_value)
            if isinstance(target, float):
                return float(raw_value)
            if callable(target):
                return target(raw_value)
            return raw_value
        except ValueError:
            raise ValueError(
                f"参数 {param_name} 类型错误。完整参数: {self.print_types()}",
            )

    def validate_and_convert_params(
        self,
        params: list[Any],
        param_type: dict[str, type],
    ) -> dict[str, Any]:
        """将参数列表 params 根据参数类型注解转换为参数字典。"""
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
            if i >= len(params):
                if param_name in self.handler_param_defaults:
                    # 参数缺失时使用默认值
                    result[param_name] = self.handler_param_defaults[param_name]
                else:
                    # 无默认值，是必填参数
                    raise ValueError(
                        f"必要参数缺失。该指令完整参数: {self.print_types()}",
                    )
            else:
                # 参数存在，按照目标类型转换
                result[param_name] = self._convert_param(
                    param_name,
                    params[i],
                    param_type_or_default_val,
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
