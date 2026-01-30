from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timedelta

from astrbot.core import logger
from astrbot.core.config.astrbot_config import RateLimitStrategy
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.node_star import NodeResult


class RateLimiter:
    """Fixed-window rate limiter (system-level mechanism)."""

    def __init__(self, ctx: PipelineContext):
        self._ctx = ctx
        self._initialized = False
        self.event_timestamps: defaultdict[str, deque[datetime]] = defaultdict(deque)
        self.locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.rate_limit_count: int = 0
        self.rate_limit_time: timedelta = timedelta(0)
        self.rl_strategy: str = ""

    async def initialize(self) -> None:
        if self._initialized:
            return
        cfg = self._ctx.astrbot_config["platform_settings"]["rate_limit"]
        self.rate_limit_count = cfg["count"]
        self.rate_limit_time = timedelta(seconds=cfg["time"])
        self.rl_strategy = cfg["strategy"]
        self._initialized = True

    async def apply(self, event: AstrMessageEvent) -> NodeResult:
        session_id = event.session_id
        now = datetime.now()

        async with self.locks[session_id]:
            while True:
                timestamps = self.event_timestamps[session_id]
                self._remove_expired_timestamps(timestamps, now)

                if len(timestamps) < self.rate_limit_count:
                    timestamps.append(now)
                    break

                next_window_time = timestamps[0] + self.rate_limit_time
                stall_duration = (next_window_time - now).total_seconds() + 0.3

                match self.rl_strategy:
                    case RateLimitStrategy.STALL.value:
                        logger.info(
                            f"会话 {session_id} 被限流。暂停 {stall_duration:.2f} 秒。"
                        )
                        await asyncio.sleep(stall_duration)
                        now = datetime.now()
                    case RateLimitStrategy.DISCARD.value:
                        logger.info(f"会话 {session_id} 被限流。此请求已被丢弃。")
                        event.stop_event()
                        return NodeResult.STOP

        return NodeResult.CONTINUE

    def _remove_expired_timestamps(
        self, timestamps: deque[datetime], now: datetime
    ) -> None:
        expiry_threshold = now - self.rate_limit_time
        while timestamps and timestamps[0] < expiry_threshold:
            timestamps.popleft()
