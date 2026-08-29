import asyncio
from collections import defaultdict, deque
from datetime import datetime, timedelta

from astrbot import logger
from astrbot.core.config.astrbot_config import RateLimitStrategy
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ..context import PipelineContext
from ..stage import Stage


class RateLimitStage(Stage):
    """检查是否需要限制消息发送的限流器。

    使用 Fixed Window 算法。
    如果触发限流，将 stall 流水线，直到下一个时间窗口来临时自动唤醒。
    """

    def __init__(self) -> None:
        # 存储每个会话的请求时间队列
        self.event_timestamps: defaultdict[str, deque[datetime]] = defaultdict(deque)
        # 为每个会话设置一个锁，避免并发冲突
        self.locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # 限流参数
        self.rate_limit_count: int = 0
        self.rate_limit_time: timedelta = timedelta(0)
        self.max_sessions: int = 10000

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
        self.max_sessions = max(
            int(
                ctx.astrbot_config["platform_settings"]["rate_limit"].get(
                    "max_sessions",
                    10000,
                )
            ),
            1,
        )

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None:
        """检查并处理限流逻辑。如果触发限流，流水线会 stall 并在窗口期后自动恢复。

        Args:
            event (AstrMessageEvent): 当前消息事件。
            ctx (PipelineContext): 流水线上下文。

        Returns:
            MessageEventResult: 继续或停止事件处理的结果。

        """
        umo = event.unified_msg_origin

        async with self.locks[umo]:  # 确保同一会话不会并发修改队列
            now = datetime.now()
            # 检查并处理限流，可能需要多次检查直到满足条件
            while True:
                timestamps = self.event_timestamps[umo]
                self._remove_expired_timestamps(timestamps, now)
                self._prune_idle_sessions(now, active_session_id=umo)

                if self.rate_limit_count <= 0:
                    break
                if len(timestamps) < self.rate_limit_count:
                    timestamps.append(now)
                    break
                next_window_time = timestamps[0] + self.rate_limit_time
                stall_duration = (next_window_time - now).total_seconds() + 0.3

                match self.rl_strategy:
                    case RateLimitStrategy.STALL.value:
                        logger.info(
                            f"会话 {umo} 被限流。根据限流策略，此会话处理将被暂停 {stall_duration:.2f} 秒。",
                        )
                        await asyncio.sleep(stall_duration)
                        now = datetime.now()
                    case RateLimitStrategy.DISCARD.value:
                        logger.info(
                            f"会话 {umo} 被限流。根据限流策略，此请求已被丢弃，直到限额于 {stall_duration:.2f} 秒后重置。",
                        )
                        return event.stop_event()

    def _prune_idle_sessions(
        self,
        now: datetime,
        *,
        active_session_id: str | None = None,
    ) -> None:
        if len(self.event_timestamps) <= self.max_sessions:
            empty_sessions = [
                session_id
                for session_id, timestamps in self.event_timestamps.items()
                if not timestamps and session_id != active_session_id
            ]
            for session_id in empty_sessions:
                self.event_timestamps.pop(session_id, None)
                self.locks.pop(session_id, None)
            return

        idle_sessions = [
            session_id
            for session_id, timestamps in self.event_timestamps.items()
            if not timestamps and session_id != active_session_id
        ]
        for session_id in idle_sessions:
            self.event_timestamps.pop(session_id, None)
            self.locks.pop(session_id, None)
            if len(self.event_timestamps) <= self.max_sessions:
                return

        sessions_by_last_seen = sorted(
            (
                (timestamps[-1], session_id)
                for session_id, timestamps in self.event_timestamps.items()
                if timestamps
            ),
        )
        while len(self.event_timestamps) > self.max_sessions and sessions_by_last_seen:
            _, session_id = sessions_by_last_seen.pop(0)
            timestamps = self.event_timestamps.get(session_id)
            if timestamps and now - timestamps[-1] > self.rate_limit_time:
                self.event_timestamps.pop(session_id, None)
                self.locks.pop(session_id, None)

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
