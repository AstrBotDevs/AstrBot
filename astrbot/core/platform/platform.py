import abc
import uuid
from asyncio import Queue
from collections.abc import Awaitable
from typing import Any

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.metrics import Metric

from .astr_message_event import AstrMessageEvent
from .message_session import MessageSesion
from .platform_metadata import PlatformMetadata


class Platform(abc.ABC):
    def __init__(self, config: dict, event_queue: Queue):
        super().__init__()
        # 平台配置
        self.config = config
        # 维护了消息平台的事件队列，EventBus 会从这里取出事件并处理。
        self._event_queue = event_queue
        self.client_self_id = uuid.uuid4().hex

    @abc.abstractmethod
    def run(self) -> Awaitable[Any]:
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
    ):
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
        当 Dashboard 收到 /platform/webhook/{uuid} 请求时，会调用此方法。

        Args:
            request: Quart 请求对象

        Returns:
            响应内容，格式取决于具体平台的要求

        Raises:
            NotImplementedError: 平台未实现统一 Webhook 模式
        """
        raise NotImplementedError(f"平台 {self.meta().name} 未实现统一 Webhook 模式")
