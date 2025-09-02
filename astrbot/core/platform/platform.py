import abc
import uuid
from typing import Awaitable, Any
from asyncio import Queue
from .platform_metadata import PlatformMetadata
from .astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageChain
from .astr_message_event import MessageSesion
from astrbot.core.utils.metrics import Metric


class Platform(abc.ABC):
    def __init__(self, event_queue: Queue):
        super().__init__()
        # 维护了消息平台的事件队列，EventBus 会从这里取出事件并处理。
        self._event_queue = event_queue
        self.client_self_id = uuid.uuid4().hex

    @abc.abstractmethod
    def run(self) -> Awaitable[Any]:
        """
        得到一个平台的运行实例，需要返回一个协程对象。
        """
        raise NotImplementedError

    async def terminate(self):
        """
        终止一个平台的运行实例。
        """
        ...

    @abc.abstractmethod
    def meta(self) -> PlatformMetadata:
        """
        得到一个平台的元数据。
        """
        raise NotImplementedError

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ) -> Awaitable[Any]:
        """
        通过会话发送消息。该方法旨在让插件能够直接通过**可持久化的会话数据**发送消息，而不需要保存 event 对象。

        异步方法。
        """
        await Metric.upload(msg_event_tick=1, adapter_name=self.meta().name)

    def commit_event(self, event: AstrMessageEvent):
        """
        提交一个事件到事件队列。
        """
        self._event_queue.put_nowait(event)

    def get_client(self):
        """
        获取平台的客户端对象。
        """
        pass
