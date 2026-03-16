"""Support helpers for runtime loader reflection and signature validation.

本模块提供运行时加载器所需的反射和签名验证工具函数，主要用于：
1. 解析 handler/capability 函数签名，提取参数类型信息
2. 识别需要注入的框架对象（如 Context、MessageEvent、ScheduleContext）
3. 构建参数规格 (ParamSpec) 供协议层使用
4. 验证 schedule handler 的签名合法性

关键函数：
- build_param_specs: 从 handler 签名构建参数规格列表
- is_injected_parameter: 判断参数是否应由框架注入而非从命令行解析
- validate_schedule_signature: 确保 schedule handler 只接受允许的注入参数
"""

from __future__ import annotations

import inspect
import typing
from typing import Any, Literal, TypeAlias, cast

from .._typing_utils import unwrap_optional
from ..decorators import get_capability_meta, get_handler_meta
from ..protocol.descriptors import ParamSpec
from ..schedule import ScheduleContext
from ..types import GreedyStr

ParamTypeName: TypeAlias = Literal[
    "str", "int", "float", "bool", "optional", "greedy_str"
]
OptionalInnerType: TypeAlias = Literal["str", "int", "float", "bool"] | None

def is_injected_parameter(annotation: Any, parameter_name: str) -> bool:
    if parameter_name in {"event", "ctx", "context", "sched", "schedule"}:
        return True
    normalized, _is_optional = unwrap_optional(annotation)
    if normalized is None:
        return False
    if normalized in {ScheduleContext}:
        return True
    if isinstance(normalized, type):
        from ..context import Context
        from ..events import MessageEvent

        return issubclass(normalized, (Context, MessageEvent, ScheduleContext))
    return False


def param_type_name(annotation: Any) -> tuple[ParamTypeName, OptionalInnerType, bool]:
    normalized, is_optional = unwrap_optional(annotation)
    if normalized is GreedyStr:
        return "greedy_str", None, False
    if normalized in {int, float, bool, str}:
        normalized_name = cast(
            Literal["str", "int", "float", "bool"], normalized.__name__
        )
        if is_optional:
            return "optional", normalized_name, False
        return normalized_name, None, True
    if is_optional:
        return "optional", "str", False
    return "str", None, True


def build_param_specs(handler: Any) -> list[ParamSpec]:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return []
    try:
        type_hints = typing.get_type_hints(handler)
    except Exception:
        type_hints = {}

    specs: list[ParamSpec] = []
    for parameter in signature.parameters.values():
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            continue
        annotation = type_hints.get(parameter.name)
        if is_injected_parameter(annotation, parameter.name):
            continue
        param_type, inner_type, required = param_type_name(annotation)
        if parameter.default is not inspect.Parameter.empty:
            required = False
        specs.append(
            ParamSpec(
                name=parameter.name,
                type=param_type,
                required=required,
                inner_type=inner_type,
            )
        )

    greedy_indexes = [
        index for index, spec in enumerate(specs) if spec.type == "greedy_str"
    ]
    if greedy_indexes and greedy_indexes[-1] != len(specs) - 1:
        greedy_spec = specs[greedy_indexes[-1]]
        raise ValueError(f"参数 '{greedy_spec.name}' (GreedyStr) 必须是最后一个参数。")
    return specs


def validate_schedule_signature(handler: Any) -> None:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return
    allowed_names = {"ctx", "context", "sched", "schedule"}
    invalid = [
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        and parameter.name not in allowed_names
    ]
    if invalid:
        raise ValueError(
            "Schedule handler 只允许注入 ctx/context 和 sched/schedule 参数。"
        )


def resolve_handler_candidate(instance: Any, name: str) -> tuple[Any, Any] | None:
    try:
        raw = inspect.getattr_static(instance, name)
    except AttributeError:
        return None
    candidates = [raw]
    wrapped = getattr(raw, "__func__", None)
    if wrapped is not None:
        candidates.append(wrapped)
    for candidate in candidates:
        meta = get_handler_meta(candidate)
        if meta is not None and meta.trigger is not None:
            return getattr(instance, name), meta
    return None


def resolve_capability_candidate(instance: Any, name: str) -> tuple[Any, Any] | None:
    try:
        raw = inspect.getattr_static(instance, name)
    except AttributeError:
        return None
    candidates = [raw]
    wrapped = getattr(raw, "__func__", None)
    if wrapped is not None:
        candidates.append(wrapped)
    for candidate in candidates:
        meta = get_capability_meta(candidate)
        if meta is not None:
            return getattr(instance, name), meta
    return None


__all__ = [
    "build_param_specs",
    "is_injected_parameter",
    "param_type_name",
    "resolve_capability_candidate",
    "resolve_handler_candidate",
    "unwrap_optional",
    "validate_schedule_signature",
]
