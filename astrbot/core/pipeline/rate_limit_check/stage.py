import asyncio
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import DefaultDict, Deque, Union, AsyncGenerator
from ..stage import Stage, register_stage
from ..context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core import logger
from astrbot.core.config.astrbot_config import RateLimitStrategy


@register_stage
class RateLimitStage(Stage):
    """
    检查是否需要限制消息发送的限流器。

    使用 Fixed Window 算法。
    如果触发限流，将 stall 流水线，直到下一个时间窗口来临时自动唤醒。
    """

    def __init__(self):
        # 存储每个会话的请求时间队列
        self.event_timestamps: DefaultDict[str, Deque[datetime]] = defaultdict(deque)
        # 为每个会话设置一个锁，避免并发冲突
        self.locks: DefaultDict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # 限流参数
        self.rate_limit_count: int = 0
        self.rate_limit_time: timedelta = timedelta(0)

    async def initialize(self, ctx: PipelineContext) -> None:
        """
        初始化限流器，根据配置设置限流参数。
        """
        self.rate_limit_count = ctx.astrbot_config["platform_settings"]["rate_limit"][
            "count"
        ]
        self.rate_limit_time = timedelta(
            seconds=ctx.astrbot_config["platform_settings"]["rate_limit"]["time"]
        )
        self.rl_strategy = ctx.astrbot_config["platform_settings"]["rate_limit"][
            "strategy"
        ]  # stall or discard

    async def process(
        self, event: AstrMessageEvent
    ) -> Union[None, AsyncGenerator[None, None]]:
        """
        检查并处理限流逻辑。如果触发限流，流水线会 stall 并在窗口期后自动恢复。

        Args:
            event (AstrMessageEvent): 当前消息事件。
            ctx (PipelineContext): 流水线上下文。

        Returns:
            MessageEventResult: 继续或停止事件处理的结果。
        """
        session_id = event.session_id
        now = datetime.now()

        async with self.locks[session_id]:  # 确保同一会话不会并发修改队列
            timestamps = self.event_timestamps[session_id]

            self._remove_expired_timestamps(timestamps, now)

            if len(timestamps) >= self.rate_limit_count:
                # 达到限流阈值，计算下一个窗口的时间
                next_window_time = timestamps[0] + self.rate_limit_time
                stall_duration = (next_window_time - now).total_seconds()

                match self.rl_strategy:
                    case RateLimitStrategy.STALL.value:
                        logger.info(
                            f"会话 {session_id} 被限流。根据限流策略，此会话处理将被暂停 {stall_duration:.2f} 秒。"
                        )
                        await asyncio.sleep(stall_duration)
                    case RateLimitStrategy.DISCARD.value:
                        # event.set_result(MessageEventResult().message(f"会话 {session_id} 被限流。根据限流策略，此请求已被丢弃，直到您的限额于 {stall_duration:.2f} 秒后重置。"))
                        logger.info(
                            f"会话 {session_id} 被限流。根据限流策略，此请求已被丢弃，直到限额于 {stall_duration:.2f} 秒后重置。"
                        )
                        return event.stop_event()

                self._remove_expired_timestamps(
                    timestamps, now + timedelta(seconds=stall_duration)
                )

            timestamps.append(now)

    def _remove_expired_timestamps(
        self, timestamps: Deque[datetime], now: datetime
    ) -> None:
        """
        移除时间窗口外的时间戳。

        Args:
            timestamps (Deque[datetime]): 当前会话的时间戳队列。
            now (datetime): 当前时间，用于计算过期时间。
        """
        expiry_threshold: datetime = now - self.rate_limit_time
        while timestamps and timestamps[0] < expiry_threshold:
            timestamps.popleft()
