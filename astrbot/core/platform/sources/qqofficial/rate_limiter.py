"""
消息回复限流器
参照 openclaw-qqbot 的 outbound.ts 实现

规则：
- 同一 message_id 1小时内最多回复 4 次
- 超过 1 小时 message_id 失效，需要降级为主动消息
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

from astrbot import logger


@dataclass
class MessageReplyRecord:
    """消息回复记录"""

    count: int = 0
    first_reply_at: float = 0.0


@dataclass
class ReplyLimitResult:
    """限流检查结果"""

    # 是否允许被动回复
    allowed: bool
    # 剩余被动回复次数
    remaining: int
    # 是否需要降级为主动消息
    should_fallback_to_proactive: bool
    # 降级原因
    fallback_reason: Optional[str] = None
    # 提示消息
    message: Optional[str] = None


class MessageReplyLimiter:
    """
    消息回复限流器

    规则：
    - 同一 message_id 1小时内最多回复 4 次
    - 超过 1 小时 message_id 失效，需要降级为主动消息
    """

    # 同一 message_id 1小时内最多回复次数
    MESSAGE_REPLY_LIMIT = 4

    # message_id 有效期（毫秒）- 1小时
    MESSAGE_REPLY_TTL_MS = 60 * 60 * 1000

    # 最大追踪消息数（避免内存泄漏）
    MAX_TRACKED_MESSAGES = 10000

    def __init__(self):
        self._tracker: Dict[str, MessageReplyRecord] = {}
        self._lock = threading.RLock()

    def check_limit(self, message_id: str) -> ReplyLimitResult:
        """
        检查是否可以回复该消息（限流检查）

        Args:
            message_id: 消息ID

        Returns:
            ReplyLimitResult: 限流检查结果
        """
        now = time.time() * 1000  # 转换为毫秒

        with self._lock:
            record = self._tracker.get(message_id)

            # 定期清理过期记录（避免内存泄漏）
            if len(self._tracker) > self.MAX_TRACKED_MESSAGES:
                self._cleanup_expired_records(now)

            # 新消息，首次回复
            if not record:
                return ReplyLimitResult(
                    allowed=True,
                    remaining=self.MESSAGE_REPLY_LIMIT,
                    should_fallback_to_proactive=False,
                )

            # 检查是否超过1小时（message_id 过期）
            if now - record.first_reply_at > self.MESSAGE_REPLY_TTL_MS:
                # 超过1小时，被动回复不可用，需要降级为主动消息
                return ReplyLimitResult(
                    allowed=False,
                    remaining=0,
                    should_fallback_to_proactive=True,
                    fallback_reason="expired",
                    message="消息已超过1小时有效期，将使用主动消息发送",
                )

            # 检查是否超过回复次数限制
            remaining = self.MESSAGE_REPLY_LIMIT - record.count
            if remaining <= 0:
                return ReplyLimitResult(
                    allowed=False,
                    remaining=0,
                    should_fallback_to_proactive=True,
                    fallback_reason="limit_exceeded",
                    message=f"该消息已达到1小时内最大回复次数({self.MESSAGE_REPLY_LIMIT}次)，将使用主动消息发送",
                )

            return ReplyLimitResult(
                allowed=True,
                remaining=remaining,
                should_fallback_to_proactive=False,
            )

    def record_reply(self, message_id: str) -> None:
        """
        记录一次消息回复

        Args:
            message_id: 消息ID
        """
        now = time.time() * 1000

        with self._lock:
            record = self._tracker.get(message_id)

            if not record:
                self._tracker[message_id] = MessageReplyRecord(
                    count=1, first_reply_at=now
                )
            else:
                # 检查是否过期，过期则重新计数
                if now - record.first_reply_at > self.MESSAGE_REPLY_TTL_MS:
                    self._tracker[message_id] = MessageReplyRecord(
                        count=1, first_reply_at=now
                    )
                else:
                    record.count += 1

            record = self._tracker.get(message_id)
            if record:
                logger.debug(
                    f"[QQOfficial] recordReply: {message_id}, count={record.count}"
                )

    def get_stats(self) -> Dict[str, int]:
        """
        获取消息回复统计信息

        Returns:
            Dict: 包含 tracked_messages 和 total_replies
        """
        with self._lock:
            total_replies = sum(r.count for r in self._tracker.values())
            return {
                "tracked_messages": len(self._tracker),
                "total_replies": total_replies,
            }

    def get_config(self) -> Dict[str, int]:
        """
        获取消息回复限制配置（供外部查询）

        Returns:
            Dict: 包含 limit, ttl_ms, ttl_hours
        """
        return {
            "limit": self.MESSAGE_REPLY_LIMIT,
            "ttl_ms": self.MESSAGE_REPLY_TTL_MS,
            "ttl_hours": self.MESSAGE_REPLY_TTL_MS // (60 * 60 * 1000),
        }

    def _cleanup_expired_records(self, now: float) -> None:
        """清理过期记录"""
        expired_keys = [
            msg_id
            for msg_id, rec in self._tracker.items()
            if now - rec.first_reply_at > self.MESSAGE_REPLY_TTL_MS
        ]
        for key in expired_keys:
            del self._tracker[key]
        if expired_keys:
            logger.debug(
                f"[QQOfficial] Cleaned up {len(expired_keys)} expired message records"
            )


# 全局限流器实例
_global_limiter: Optional[MessageReplyLimiter] = None
_global_limiter_lock = threading.RLock()


def get_rate_limiter() -> MessageReplyLimiter:
    """获取全局限流器实例"""
    global _global_limiter
    with _global_limiter_lock:
        if _global_limiter is None:
            _global_limiter = MessageReplyLimiter()
        return _global_limiter


def check_message_reply_limit(message_id: str) -> ReplyLimitResult:
    """
    检查是否可以回复该消息（便捷函数）

    Args:
        message_id: 消息ID

    Returns:
        ReplyLimitResult: 限流检查结果
    """
    return get_rate_limiter().check_limit(message_id)


def record_message_reply(message_id: str) -> None:
    """
    记录一次消息回复（便捷函数）

    Args:
        message_id: 消息ID
    """
    get_rate_limiter().record_reply(message_id)
