"""TTS 文本过滤器：在发送 TTS 前去除括号/标记等内容。"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TypeVar

    T = TypeVar("T")

from astrbot.core import logger


class TTSTextFilter:
    """过滤 TTS 文本中的括号内容。"""

    # 内置默认规则：匹配各种括号及其内容
    BUILTIN_PATTERNS: list[str] = [
        r"\*\*[^*]+\*\*",  # **文字**
        r"\*[^*]+\*",  # *文字*
        r"\([^)]*\)",  # (文字) 英文/半角括号
        r"（[^）]*）",  # （文字）中文括号
        r"【[^】]*】",  # 【文字】
        r"\[[^\]]*\]",  # [文字]
    ]

    @classmethod
    def apply(cls, text: str, custom_rules: list[str] | None = None) -> str:
        """应用内置规则和自定义规则，返回过滤后的文本。

        如果 custom_rules 中包含无效的正则表达式，会记录警告日志并跳过该规则。
        """
        result = text
        all_rules = cls.BUILTIN_PATTERNS + (custom_rules or [])
        for i, pattern in enumerate(all_rules):
            try:
                result = re.sub(pattern, "", result)
            except re.error:
                is_custom = i >= len(cls.BUILTIN_PATTERNS)
                if is_custom and custom_rules:
                    idx = i - len(cls.BUILTIN_PATTERNS)
                    logger.warning(
                        f"[TTSTextFilter] 自定义正则规则 #{idx} 无效，已跳过: {pattern}"
                    )
                # 内置规则出错不记录日志（几乎不会发生）
        return result.strip()


class FilteredQueue:
    """异步队列包装器，在 get() 时自动过滤文本。

    用于 TTS 流式场景：Feeder 写入原始文本（用于日志/UI），
    TTS 消费者读取过滤后的文本。
    不继承 asyncio.Queue，而是通过组合模式包装真实队列。
    """

    def __init__(
        self,
        real_queue: asyncio.Queue,
        custom_rules: list[str] | None = None,
    ) -> None:
        self._real_queue = real_queue
        self._custom_rules = custom_rules

    async def get(self) -> str | None:
        while True:
            item = await self._real_queue.get()
            if item is None:
                return None
            if isinstance(item, str):
                filtered = TTSTextFilter.apply(item, self._custom_rules)
                if filtered:
                    return filtered
                continue
            return item

    def qsize(self) -> int:
        return self._real_queue.qsize()

    def empty(self) -> bool:
        return self._real_queue.empty()

    def full(self) -> bool:
        return self._real_queue.full()

    async def put(self, item) -> None:
        await self._real_queue.put(item)

    def task_done(self) -> None:
        self._real_queue.task_done()

    async def join(self) -> None:
        await self._real_queue.join()
