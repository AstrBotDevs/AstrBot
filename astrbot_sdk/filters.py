"""SDK-native filter declarations.

本模块提供事件过滤器的声明式 API，用于在 handler 执行前进行条件判断。

内置过滤器类型：
- PlatformFilter: 按平台名称过滤（如 qq、wechat）
- MessageTypeFilter: 按消息类型过滤（如 group、private）
- CustomFilter: 用户自定义的同步布尔函数

组合操作：
- all_of(*filters): 所有过滤器都通过才执行（AND 逻辑）
- any_of(*filters): 任一过滤器通过即可执行（OR 逻辑）
- 支持 & 和 | 运算符进行链式组合

过滤器在本地（SDK worker 进程内）求值，避免不必要的跨进程调用。
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from .decorators import append_filter_meta
from .protocol.descriptors import (
    CompositeFilterSpec,
    FilterSpec,
    LocalFilterRefSpec,
    MessageTypeFilterSpec,
    PlatformFilterSpec,
)

FilterOperator: TypeAlias = Literal["and", "or"]


@dataclass(slots=True)
class LocalFilterBinding:
    filter_id: str
    callable: Callable[..., bool]
    args: dict[str, Any] = field(default_factory=dict)

    def evaluate(self, *, event=None, ctx=None) -> bool:
        signature = inspect.signature(self.callable)
        kwargs: dict[str, Any] = {}
        if "event" in signature.parameters:
            kwargs["event"] = event
        if "ctx" in signature.parameters:
            kwargs["ctx"] = ctx
        result = self.callable(**kwargs)
        if inspect.isawaitable(result):
            raise TypeError("CustomFilter must return a synchronous bool")
        if not isinstance(result, bool):
            raise TypeError("CustomFilter must return bool")
        return result


class FilterBinding:
    def __and__(self, other: FilterBinding) -> CompositeFilter:
        return CompositeFilter("and", [self, other])

    def __or__(self, other: FilterBinding) -> CompositeFilter:
        return CompositeFilter("or", [self, other])

    def compile(self) -> tuple[FilterSpec, list[LocalFilterBinding]]:
        raise NotImplementedError


@dataclass(slots=True)
class PlatformFilter(FilterBinding):
    platforms: list[str]

    def compile(self) -> tuple[FilterSpec, list[LocalFilterBinding]]:
        return PlatformFilterSpec(platforms=list(self.platforms)), []


@dataclass(slots=True)
class MessageTypeFilter(FilterBinding):
    message_types: list[str]

    def compile(self) -> tuple[FilterSpec, list[LocalFilterBinding]]:
        return MessageTypeFilterSpec(message_types=list(self.message_types)), []


@dataclass(slots=True)
class CustomFilter(FilterBinding):
    callable: Callable[..., bool]
    filter_id: str | None = None

    def __post_init__(self) -> None:
        if self.filter_id is None:
            self.filter_id = f"{self.callable.__module__}.{getattr(self.callable, '__qualname__', self.callable.__name__)}"

    def compile(self) -> tuple[FilterSpec, list[LocalFilterBinding]]:
        assert self.filter_id is not None
        return LocalFilterRefSpec(filter_id=self.filter_id), [
            LocalFilterBinding(filter_id=self.filter_id, callable=self.callable),
        ]


@dataclass(slots=True)
class CompositeFilter(FilterBinding):
    operator: FilterOperator
    children: list[FilterBinding]

    def compile(self) -> tuple[FilterSpec, list[LocalFilterBinding]]:
        compiled_children: list[FilterSpec] = []
        local_bindings: list[LocalFilterBinding] = []
        for child in self.children:
            spec, locals_for_child = child.compile()
            compiled_children.append(spec)
            local_bindings.extend(locals_for_child)

        if local_bindings:
            filter_id = (
                "composite:"
                + ":".join(binding.filter_id for binding in local_bindings)
                + f":{self.operator}"
            )

            def _evaluate(*, event=None, ctx=None) -> bool:
                results = [
                    _evaluate_filter_spec_locally(
                        spec, local_bindings, event=event, ctx=ctx
                    )
                    for spec in compiled_children
                ]
                if self.operator == "and":
                    return all(results)
                return any(results)

            return (
                LocalFilterRefSpec(filter_id=filter_id),
                [LocalFilterBinding(filter_id=filter_id, callable=_evaluate)],
            )

        return CompositeFilterSpec(kind=self.operator, children=compiled_children), []


def _evaluate_filter_spec_locally(
    spec: FilterSpec,
    local_bindings: list[LocalFilterBinding],
    *,
    event=None,
    ctx=None,
) -> bool:
    if isinstance(spec, PlatformFilterSpec):
        if event is None:
            return True
        platform = getattr(event, "platform", "") or ""
        return platform in spec.platforms
    if isinstance(spec, MessageTypeFilterSpec):
        if event is None:
            return True
        message_type = getattr(event, "message_type", "") or ""
        return message_type in spec.message_types
    if isinstance(spec, LocalFilterRefSpec):
        binding = next(
            (item for item in local_bindings if item.filter_id == spec.filter_id),
            None,
        )
        if binding is None:
            return True
        return binding.evaluate(event=event, ctx=ctx)
    if isinstance(spec, CompositeFilterSpec):
        results = [
            _evaluate_filter_spec_locally(
                child,
                local_bindings,
                event=event,
                ctx=ctx,
            )
            for child in spec.children
        ]
        if spec.kind == "and":
            return all(results)
        return any(results)
    return True


def custom_filter(
    binding: FilterBinding,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Attach a filter declaration to a handler."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        spec, local_bindings = binding.compile()
        append_filter_meta(
            func,
            specs=[spec],
            local_bindings=local_bindings,
        )
        return func

    return decorator


def all_of(*bindings: FilterBinding) -> CompositeFilter:
    return CompositeFilter("and", list(bindings))


def any_of(*bindings: FilterBinding) -> CompositeFilter:
    return CompositeFilter("or", list(bindings))


__all__ = [
    "CustomFilter",
    "FilterBinding",
    "LocalFilterBinding",
    "MessageTypeFilter",
    "PlatformFilter",
    "all_of",
    "any_of",
    "custom_filter",
]
