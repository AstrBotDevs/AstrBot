from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

T = TypeVar("T")


async def resolve_maybe_awaitable(value: T | Awaitable[T]) -> T:
    while inspect.isawaitable(value):
        value = await cast(Awaitable[T], value)
    return cast(T, value)


async def run_maybe_async(
    operation: Callable[[], T | Awaitable[T]] | T | Awaitable[T],
) -> T:
    result: Any = operation() if callable(operation) else operation
    return await resolve_maybe_awaitable(result)
