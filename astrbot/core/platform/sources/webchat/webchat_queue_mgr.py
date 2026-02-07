import asyncio
from collections.abc import Awaitable, Callable

from astrbot import logger


class WebChatQueueMgr:
    def __init__(self, queue_maxsize: int = 128, back_queue_maxsize: int = 512) -> None:
        self.queues: dict[str, asyncio.Queue] = {}
        """Conversation ID to asyncio.Queue mapping"""
        self.back_queues: dict[str, asyncio.Queue] = {}
        """Request ID to asyncio.Queue mapping for responses"""
        self._conversation_back_requests: dict[str, set[str]] = {}
        self._request_conversation: dict[str, str] = {}
        self._queue_close_events: dict[str, asyncio.Event] = {}
        self._listener_tasks: dict[str, asyncio.Task] = {}
        self._listener_callback: Callable[[tuple], Awaitable[None]] | None = None
        self.queue_maxsize = queue_maxsize
        self.back_queue_maxsize = back_queue_maxsize

    def get_or_create_queue(self, conversation_id: str) -> asyncio.Queue:
        """Get or create a queue for the given conversation ID"""
        if conversation_id not in self.queues:
            self.queues[conversation_id] = asyncio.Queue(maxsize=self.queue_maxsize)
            self._queue_close_events[conversation_id] = asyncio.Event()
            self._start_listener_if_needed(conversation_id)
        return self.queues[conversation_id]

    def get_or_create_back_queue(
        self,
        request_id: str,
        conversation_id: str | None = None,
    ) -> asyncio.Queue:
        """Get or create a back queue for the given request ID"""
        if request_id not in self.back_queues:
            self.back_queues[request_id] = asyncio.Queue(
                maxsize=self.back_queue_maxsize
            )
        if conversation_id:
            self._request_conversation[request_id] = conversation_id
            if conversation_id not in self._conversation_back_requests:
                self._conversation_back_requests[conversation_id] = set()
            self._conversation_back_requests[conversation_id].add(request_id)
        return self.back_queues[request_id]

    def remove_back_queue(self, request_id: str):
        """Remove back queue for the given request ID"""
        self.back_queues.pop(request_id, None)
        conversation_id = self._request_conversation.pop(request_id, None)
        if conversation_id:
            request_ids = self._conversation_back_requests.get(conversation_id)
            if request_ids is not None:
                request_ids.discard(request_id)
                if not request_ids:
                    self._conversation_back_requests.pop(conversation_id, None)

    def remove_queues(self, conversation_id: str):
        """Remove queues for the given conversation ID"""
        for request_id in list(
            self._conversation_back_requests.get(conversation_id, set())
        ):
            self.remove_back_queue(request_id)
        self._conversation_back_requests.pop(conversation_id, None)
        self.remove_queue(conversation_id)

    def remove_queue(self, conversation_id: str):
        """Remove input queue and listener for the given conversation ID"""
        self.queues.pop(conversation_id, None)

        close_event = self._queue_close_events.pop(conversation_id, None)
        if close_event is not None:
            close_event.set()

        task = self._listener_tasks.pop(conversation_id, None)
        if task is not None:
            task.cancel()

    def has_queue(self, conversation_id: str) -> bool:
        """Check if a queue exists for the given conversation ID"""
        return conversation_id in self.queues

    def set_listener(
        self,
        callback: Callable[[tuple], Awaitable[None]],
    ):
        self._listener_callback = callback
        for conversation_id in list(self.queues.keys()):
            self._start_listener_if_needed(conversation_id)

    def _start_listener_if_needed(self, conversation_id: str):
        if self._listener_callback is None:
            return
        if conversation_id in self._listener_tasks:
            task = self._listener_tasks[conversation_id]
            if not task.done():
                return
        queue = self.queues.get(conversation_id)
        close_event = self._queue_close_events.get(conversation_id)
        if queue is None or close_event is None:
            return
        task = asyncio.create_task(
            self._listen_to_queue(conversation_id, queue, close_event),
            name=f"webchat_listener_{conversation_id}",
        )
        self._listener_tasks[conversation_id] = task
        task.add_done_callback(
            lambda _: self._listener_tasks.pop(conversation_id, None)
        )
        logger.debug(f"Started listener for conversation: {conversation_id}")

    async def _listen_to_queue(
        self,
        conversation_id: str,
        queue: asyncio.Queue,
        close_event: asyncio.Event,
    ):
        while True:
            get_task = asyncio.create_task(queue.get())
            close_task = asyncio.create_task(close_event.wait())
            try:
                done, pending = await asyncio.wait(
                    {get_task, close_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                if close_task in done:
                    break
                data = get_task.result()
                if self._listener_callback is None:
                    continue
                try:
                    await self._listener_callback(data)
                except Exception as e:
                    logger.error(
                        f"Error processing message from conversation {conversation_id}: {e}"
                    )
            except asyncio.CancelledError:
                break
            finally:
                if not get_task.done():
                    get_task.cancel()
                if not close_task.done():
                    close_task.cancel()


webchat_queue_mgr = WebChatQueueMgr()
