import asyncio
import time
from collections import defaultdict, deque
from collections.abc import AsyncGenerator
from datetime import timedelta

from astrbot.core import logger
from astrbot.core.config.astrbot_config import RateLimitStrategy
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ..context import PipelineContext
from ..stage import Stage, register_stage


@register_stage
class RateLimitStage(Stage):
    """Fixed-window per-session rate limiter stage."""

    _SWEEP_ENTRY_THRESHOLD = 256
    _MIN_SWEEP_INTERVAL = 1.0

    def __init__(self) -> None:
        # 存储每个会话的请求时间队列（使用 monotonic 秒数，避免系统时钟跳变影响）
        self.event_timestamps: defaultdict[str, deque[float]] = defaultdict(deque)
        # 为每个会话设置一个锁，避免并发冲突
        self.locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock_waiters: defaultdict[str, int] = defaultdict(int)
        self._last_sweep: float = 0.0
        # 限流参数
        self.rate_limit_count: int = 0
        self.rate_limit_time: timedelta = timedelta(0)
        self.rl_strategy: str = RateLimitStrategy.STALL.value

    async def initialize(self, ctx: PipelineContext) -> None:
        """初始化限流器，根据配置设置限流参数。"""
        self.rate_limit_count = ctx.astrbot_config["platform_settings"]["rate_limit"][
            "count"
        ]
        self.rate_limit_time = timedelta(
            seconds=ctx.astrbot_config["platform_settings"]["rate_limit"]["time"],
        )
        self.rl_strategy = ctx.astrbot_config["platform_settings"]["rate_limit"][
            "strategy"
        ]  # stall or discard

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        """检查并处理限流逻辑。如果触发限流，流水线会 stall 并在窗口期后自动恢复。

        Args:
            event (AstrMessageEvent): 当前消息事件。

        """
        window_seconds = self.rate_limit_time.total_seconds()
        if self.rate_limit_count <= 0 or window_seconds <= 0:
            return

        now = time.monotonic()
        if now - self._last_sweep >= max(window_seconds, 60.0) or (
            len(self.event_timestamps) >= self._SWEEP_ENTRY_THRESHOLD
            and now - self._last_sweep >= self._MIN_SWEEP_INTERVAL
        ):
            self._sweep_expired_sessions(now, window_seconds)

        umo = event.unified_msg_origin
        self._lock_waiters[umo] += 1
        lock = self.locks[umo]
        try:
            async with lock:  # 确保同一会话不会并发修改队列
                now = time.monotonic()
                # 检查并处理限流，可能需要多次检查直到满足条件
                while True:
                    window_seconds = self.rate_limit_time.total_seconds()
                    timestamps = self.event_timestamps[umo]
                    self._remove_expired_timestamps(timestamps, now, window_seconds)

                    if self.rate_limit_count <= 0 or window_seconds <= 0:
                        break
                    if len(timestamps) < self.rate_limit_count:
                        timestamps.append(now)
                        break
                    next_window_time = timestamps[0] + window_seconds
                    stall_duration = max(0.0, next_window_time - now) + 0.3

                    match self.rl_strategy:
                        case RateLimitStrategy.STALL.value:
                            logger.info(
                                f"Session {umo} was rate-limited. Processing will "
                                f"pause for {stall_duration:.2f} seconds according to the "
                                "rate-limit policy.",
                            )
                            await asyncio.sleep(stall_duration)
                            now = time.monotonic()
                        case RateLimitStrategy.DISCARD.value:
                            logger.info(
                                f"Session {umo} was rate-limited. This request was "
                                "discarded according to the rate-limit policy; the limit "
                                f"resets in {stall_duration:.2f} seconds.",
                            )
                            return event.stop_event()
                        case _:
                            logger.warning(
                                f"Unknown rate-limit strategy {self.rl_strategy!r} for "
                                f"session {umo}; discarding event.",
                            )
                            return event.stop_event()
        finally:
            remaining = self._lock_waiters.get(umo, 0) - 1
            if remaining <= 0:
                self._lock_waiters.pop(umo, None)
                timestamps = self.event_timestamps.get(umo)
                if not timestamps:
                    self.event_timestamps.pop(umo, None)
                    self.locks.pop(umo, None)
            else:
                self._lock_waiters[umo] = remaining

    def _sweep_expired_sessions(self, now: float, window_seconds: float) -> None:
        """Evict expired timestamps and idle session locks."""
        self._last_sweep = now
        for umo in list(self.event_timestamps):
            timestamps = self.event_timestamps[umo]
            self._remove_expired_timestamps(timestamps, now, window_seconds)
            if not timestamps and self._lock_waiters.get(umo, 0) == 0:
                self.event_timestamps.pop(umo, None)
                self.locks.pop(umo, None)
                self._lock_waiters.pop(umo, None)

    def _remove_expired_timestamps(
        self,
        timestamps: deque[float],
        now: float,
        window_seconds: float | None = None,
    ) -> None:
        """Remove timestamps older than the active rate-limit window.

        Args:
            timestamps: Monotonic timestamp queue for a session.
            now: Current monotonic timestamp in seconds.
            window_seconds: Rate-limit window length in seconds.
        """
        effective_window = (
            self.rate_limit_time.total_seconds()
            if window_seconds is None
            else window_seconds
        )
        expiry_threshold = now - effective_window
        while timestamps and timestamps[0] < expiry_threshold:
            timestamps.popleft()
