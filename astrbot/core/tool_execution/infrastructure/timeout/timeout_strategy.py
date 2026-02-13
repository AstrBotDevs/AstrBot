"""超时策略

实现超时控制的策略模式。
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

from astrbot.core.tool_execution.interfaces import ITimeoutStrategy


class TimeoutStrategy(ITimeoutStrategy):
    """标准超时策略"""

    async def execute(self, coro: Coroutine, timeout: float) -> Any:
        """执行带超时的协程"""
        return await asyncio.wait_for(coro, timeout=timeout)


class NoTimeoutStrategy(ITimeoutStrategy):
    """无超时策略"""

    async def execute(self, coro: Coroutine, timeout: float) -> Any:
        """直接执行协程，忽略超时参数"""
        return await coro
