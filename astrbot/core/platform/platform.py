import abc
import uuid
from asyncio import Queue
from collections.abc import Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.metrics import Metric

from .astr_message_event import AstrMessageEvent
from .message_session import MessageSesion
from .platform_metadata import PlatformMetadata


class PlatformStatus(Enum):
    """平台运行状态"""

    PENDING = "pending"  # 待启动
    RUNNING = "running"  # 运行中
    ERROR = "error"  # 发生错误
    STOPPED = "stopped"  # 已停止


@dataclass
class PlatformError:
    """平台错误信息"""

    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    traceback: str | None = None


class Platform(abc.ABC):
    def __init__(self, config: dict, event_queue: Queue):
        super().__init__()
        # 平台配置
        self.config = config
        # 维护了消息平台的事件队列，EventBus 会从这里取出事件并处理。
        self._event_queue = event_queue
        self.client_self_id = uuid.uuid4().hex

        # 平台运行状态
        self._status: PlatformStatus = PlatformStatus.PENDING
        self._errors: list[PlatformError] = []
        self._started_at: datetime | None = None

    @property
    def status(self) -> PlatformStatus:
        """获取平台运行状态"""
        return self._status

    @status.setter
    def status(self, value: PlatformStatus):
        """设置平台运行状态"""
        self._status = value
        if value == PlatformStatus.RUNNING and self._started_at is None:
            self._started_at = datetime.now()

    @property
    def errors(self) -> list[PlatformError]:
        """获取错误列表"""
        return self._errors

    @property
    def last_error(self) -> PlatformError | None:
        """获取最近的错误"""
        return self._errors[-1] if self._errors else None

    def record_error(self, message: str, traceback_str: str | None = None):
        """记录一个错误"""
        self._errors.append(PlatformError(message=message, traceback=traceback_str))
        self._status = PlatformStatus.ERROR

    def clear_errors(self):
        """清除错误记录"""
        self._errors.clear()
        if self._status == PlatformStatus.ERROR:
            self._status = PlatformStatus.RUNNING

    def unified_webhook(self) -> bool:
        """是否正在使用统一 Webhook 模式"""
        return bool(
            self.config.get("unified_webhook_mode", False)
            and self.config.get("webhook_uuid")
        )

    def get_stats(self) -> dict:
        """获取平台统计信息"""
        meta = self.meta()
        return {
            "id": meta.id or self.config.get("id"),
            "type": meta.name,
            "display_name": meta.adapter_display_name or meta.name,
            "status": self._status.value,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "error_count": len(self._errors),
            "last_error": {
                "message": self.last_error.message,
                "timestamp": self.last_error.timestamp.isoformat(),
                "traceback": self.last_error.traceback,
            }
            if self.last_error
            else None,
            "unified_webhook": self.unified_webhook(),
        }

    @abc.abstractmethod
    def run(self) -> Coroutine[Any, Any, None]:
        """得到一个平台的运行实例，需要返回一个协程对象。"""
        raise NotImplementedError

    async def terminate(self):
        """终止一个平台的运行实例。"""

    @abc.abstractmethod
    def meta(self) -> PlatformMetadata:
        """得到一个平台的元数据。"""
        raise NotImplementedError

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        """通过会话发送消息。该方法旨在让插件能够直接通过**可持久化的会话数据**发送消息，而不需要保存 event 对象。

        异步方法。
        """
        await Metric.upload(msg_event_tick=1, adapter_name=self.meta().name)

    def commit_event(self, event: AstrMessageEvent):
        """提交一个事件到事件队列。"""
        self._event_queue.put_nowait(event)

    def get_client(self):
        """获取平台的客户端对象。"""

    async def webhook_callback(self, request: Any) -> Any:
        """统一 Webhook 回调入口。

        支持统一 Webhook 模式的平台需要实现此方法。
        当 Dashboard 收到 /api/platform/webhook/{uuid} 请求时，会调用此方法。

        Args:
            request: Quart 请求对象

        Returns:
            响应内容，格式取决于具体平台的要求

        Raises:
            NotImplementedError: 平台未实现统一 Webhook 模式
        """
        raise NotImplementedError(f"平台 {self.meta().name} 未实现统一 Webhook 模式")
