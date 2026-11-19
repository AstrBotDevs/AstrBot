import asyncio
from collections import defaultdict, deque
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta

from astrbot.core import logger
from astrbot.core.config.astrbot_config import RateLimitStrategy
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ..context import PipelineContext
from ..stage import Stage, register_stage


@register_stage
class RateLimitStage(Stage):
    """Limit admitted messages and bound per-session rate-limit waiters."""

    def __init__(self) -> None:
        # 存储每个会话的请求时间队列
        self.event_timestamps: defaultdict[str, deque[datetime]] = defaultdict(deque)
        # 为每个会话设置一个锁，避免并发冲突
        self.locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # 限流参数
        self.rate_limit_count: int = 0
        self.rate_limit_time: timedelta = timedelta(0)
        self.max_pending = 1
        self._pending_events: dict[str, int] = {}

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
        self.max_pending = max(
            0,
            int(
                ctx.astrbot_config["platform_settings"]["rate_limit"].get(
                    "max_pending", 1
                )
            ),
        )

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        """Admit immediately, discard, or join a bounded per-session wait.

        Args:
            event: Incoming message event.

        Returns:
            None after admission or after stopping an excess event.
        """
        if self.rate_limit_count <= 0:
            return

        umo = event.unified_msg_origin

        now = datetime.now()
        timestamps = self.event_timestamps[umo]
        self._remove_expired_timestamps(timestamps, now)
        pending = self._pending_events.get(umo, 0)

        # No await separates checking and reserving capacity in this event loop.
        # Do not let new arrivals overtake existing stall waiters.
        if not pending and len(timestamps) < self.rate_limit_count:
            timestamps.append(now)
            return

        if (
            self.rl_strategy == RateLimitStrategy.DISCARD.value
            or pending >= self.max_pending
        ):
            logger.info(
                f"Session {umo} was rate-limited. This request was discarded "
                "without waiting for rate-limit capacity."
            )
            return event.stop_event()

        # Reserve before acquiring the lock: lock waiters must count too.
        self._pending_events[umo] = pending + 1
        try:
            async with self.locks[umo]:
                now = datetime.now()
                while True:
                    timestamps = self.event_timestamps[umo]
                    self._remove_expired_timestamps(timestamps, now)
                    if self.rate_limit_count <= 0:
                        break
                    if len(timestamps) < self.rate_limit_count:
                        timestamps.append(now)
                        break
                    next_window_time = timestamps[0] + self.rate_limit_time
                    stall_duration = (next_window_time - now).total_seconds() + 0.3
                    logger.info(
                        f"Session {umo} was rate-limited. Processing will "
                        f"pause for {stall_duration:.2f} seconds according to the "
                        "rate-limit policy."
                    )
                    await asyncio.sleep(stall_duration)
                    now = datetime.now()
        finally:
            remaining = self._pending_events[umo] - 1
            if remaining:
                self._pending_events[umo] = remaining
            else:
                del self._pending_events[umo]

    def _remove_expired_timestamps(
        self,
        timestamps: deque[datetime],
        now: datetime,
    ) -> None:
        """移除时间窗口外的时间戳。

        Args:
            timestamps (Deque[datetime]): 当前会话的时间戳队列。
            now (datetime): 当前时间，用于计算过期时间。

        """
        expiry_threshold: datetime = now - self.rate_limit_time
        while timestamps and timestamps[0] < expiry_threshold:
            timestamps.popleft()
