"""完成信号

替代轮询的事件驱动等待机制。
"""

import asyncio

from astrbot.core.tool_execution.interfaces import ICompletionSignal


class CompletionSignal(ICompletionSignal):
    """完成信号实现"""

    def __init__(self):
        self._event = asyncio.Event()

    async def wait(self, timeout: float | None = None) -> bool:
        """等待信号"""
        try:
            await asyncio.wait_for(self._event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def set(self) -> None:
        """设置信号"""
        self._event.set()

    def clear(self) -> None:
        """清除信号"""
        self._event.clear()
