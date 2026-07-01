"""Shared stream execution primitives for runtime internals.

本模块定义流式执行的通用数据结构 StreamExecution，用于：
1. 封装异步生成器迭代器，支持逐块返回数据
2. 提供收集完成后的聚合回调 (finalize)
3. 控制是否需要在内存中累积所有分块

使用场景：
- LLM 流式对话返回逐字输出
- DB watch 监听键值变更流
- 任何需要分块返回而非一次性返回的能力调用
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class StreamExecution:
    iterator: AsyncIterator[dict[str, Any]]
    finalize: Callable[[list[dict[str, Any]]], dict[str, Any]]
    collect_chunks: bool = True


__all__ = ["StreamExecution"]
