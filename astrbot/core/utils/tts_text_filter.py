"""TTS 文本过滤器：在发送 TTS 前去除括号/标记等内容。"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TypeVar

    T = TypeVar("T")


class TTSTextFilter:
    """过滤 TTS 文本中的括号内容。"""

    # 内置默认规则：匹配各种括号及其内容
    BUILTIN_PATTERNS: list[str] = [
        r"\*\*[^*]+\*\*",  # **文字**
        r"\*[^*]+\*",      # *文字*
        r"\([^)]*\)",      # (文字) 英文/半角括号
        r"（[^）]*）",      # （文字）中文括号
        r"【[^】]*】",      # 【文字】
        r"\[[^\]]*\]",     # [文字]
    ]

    @classmethod
    def apply(cls, text: str, custom_rules: list[str] | None = None) -> str:
        """应用内置规则和自定义规则，返回过滤后的文本。"""
        result = text
        all_rules = cls.BUILTIN_PATTERNS + (custom_rules or [])
        for pattern in all_rules:
            try:
                result = re.sub(pattern, "", result)
            except re.error:
                pass
        return result.strip()


class FilteredQueue(asyncio.Queue):
    """异步队列包装器，在 get() 时自动过滤文本。

    用于 TTS 流式场景：Feeder 写入原始文本（用于日志/UI），
    TTS 消费者读取过滤后的文本。
    """

    def __init__(
        self,
        real_queue: asyncio.Queue[T | None],
        custom_rules: list[str] | None = None,
    ) -> None:
        self._real_queue = real_queue
        self._custom_rules = custom_rules

    async def get(self) -> T | None:
        item = await self._real_queue.get()
        if item is None:
            return None
        if isinstance(item, str):
            return TTSTextFilter.apply(item, self._custom_rules)  # type: ignore[return-value]
        return item

    def qsize(self) -> int:
        return self._real_queue.qsize()

    def empty(self) -> bool:
        return self._real_queue.empty()

    def full(self) -> bool:
        return self._real_queue.full()

    async def put(self, item: T | None) -> None:
        await self._real_queue.put(item)

    def task_done(self) -> None:
        self._real_queue.task_done()

    async def join(self) -> None:
        await self._real_queue.join()
