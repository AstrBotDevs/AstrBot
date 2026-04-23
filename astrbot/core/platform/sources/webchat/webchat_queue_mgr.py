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
        self._request_sender: dict[str, str] = {}
        self._queue_close_events: dict[str, asyncio.Event] = {}
        self._listener_tasks: dict[str, asyncio.Task] = {}
        self._listener_callbacks: dict[str, Callable[[tuple], Awaitable[None]]] = {}
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

    def bind_back_queue(
        self,
        request_id: str,
        queue: asyncio.Queue,
        conversation_id: str | None = None,
    ) -> None:
        """Bind a request ID to an existing back queue."""
        self.back_queues[request_id] = queue
        if conversation_id:
            self._request_conversation[request_id] = conversation_id
            if conversation_id not in self._conversation_back_requests:
                self._conversation_back_requests[conversation_id] = set()
            self._conversation_back_requests[conversation_id].add(request_id)

    def remove_back_queue(self, request_id: str):
        """Remove back queue for the given request ID"""
        self.back_queues.pop(request_id, None)
        self._request_sender.pop(request_id, None)
        conversation_id = self._request_conversation.pop(request_id, None)
        if conversation_id:
            request_ids = self._conversation_back_requests.get(conversation_id)
            if request_ids is not None:
                request_ids.discard(request_id)
                if not request_ids:
                    self._conversation_back_requests.pop(conversation_id, None)

    def remove_queues(self, conversation_id: str) -> None:
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

    def bind_request_sender(self, request_id: str, sender_id: str | None) -> None:
        """Bind a request ID to the bot that will answer it."""
        if sender_id:
            self._request_sender[request_id] = sender_id

    def list_back_request_ids(
        self,
        conversation_id: str,
        sender_id: str | None = None,
    ) -> list[str]:
        """List active back-queue request IDs for a conversation."""
        request_ids = list(self._conversation_back_requests.get(conversation_id, set()))
        if sender_id is None:
            return request_ids
        return [
            request_id
            for request_id in request_ids
            if self._request_sender.get(request_id) == sender_id
        ]

    def has_queue(self, conversation_id: str) -> bool:
        """Check if a queue exists for the given conversation ID"""
        return conversation_id in self.queues

    def set_listener(
        self,
        platform_id: str,
        callback: Callable[[tuple], Awaitable[None]],
    ):
        self._listener_callbacks[platform_id] = callback
        for conversation_id in list(self.queues.keys()):
            self._start_listener_if_needed(conversation_id)

    async def clear_listener(self, platform_id: str) -> None:
        self._listener_callbacks.pop(platform_id, None)
        if self._listener_callbacks:
            return

        for close_event in list(self._queue_close_events.values()):
            close_event.set()
        self._queue_close_events.clear()

        listener_tasks = list(self._listener_tasks.values())
        for task in listener_tasks:
            task.cancel()
        if listener_tasks:
            await asyncio.gather(*listener_tasks, return_exceptions=True)
        self._listener_tasks.clear()

    def _start_listener_if_needed(self, conversation_id: str):
        if not self._listener_callbacks:
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
                if not self._listener_callbacks:
                    continue
                if self._is_adapter_broadcast(data):
                    await self._broadcast_to_adapters(data)
                    continue
                target_platform_id = self._target_platform_id(data)
                callback = self._listener_callbacks.get(target_platform_id)
                if callback is None:
                    callback = self._listener_callbacks.get("webchat")
                if callback is None:
                    logger.warning(
                        "No webchat listener for target platform: %s",
                        target_platform_id,
                    )
                    continue
                try:
                    await callback(data)
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

    @staticmethod
    def _target_platform_id(data: tuple) -> str:
        try:
            _, _, payload = data
            if isinstance(payload, dict):
                return str(payload.get("target_platform_id") or "webchat")
        except Exception:
            pass
        return "webchat"

    @staticmethod
    def _is_adapter_broadcast(data: tuple) -> bool:
        try:
            _, _, payload = data
            return isinstance(payload, dict) and bool(payload.get("broadcast_adapters"))
        except Exception:
            return False

    async def _broadcast_to_adapters(self, data: tuple) -> None:
        try:
            username, conversation_id, payload = data
        except Exception:
            return
        if not isinstance(payload, dict):
            return

        platform_ids = payload.get("broadcast_platform_ids")
        if isinstance(platform_ids, list):
            target_platform_ids = [str(pid) for pid in platform_ids if pid]
        else:
            source_platform_id = str(payload.get("source_platform_id") or "")
            target_platform_ids = [
                platform_id
                for platform_id in self._listener_callbacks
                if platform_id != "webchat" and platform_id != source_platform_id
            ]

        for platform_id in target_platform_ids:
            callback = self._listener_callbacks.get(platform_id)
            if callback is None:
                logger.warning(
                    "No webchat listener for broadcast platform: %s",
                    platform_id,
                )
                continue
            broadcast_payload = dict(payload)
            broadcast_payload["receiver_platform_id"] = platform_id
            broadcast_payload.pop("target_platform_id", None)
            broadcast_payload.pop("target_bot_id", None)
            try:
                await callback((username, conversation_id, broadcast_payload))
            except Exception as e:
                logger.error(
                    f"Error broadcasting message to platform {platform_id}: {e}",
                )


webchat_queue_mgr = WebChatQueueMgr()
