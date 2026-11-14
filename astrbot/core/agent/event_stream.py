"""Storage-independent runner events and acknowledged delivery."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from copy import deepcopy
from typing import Generic, TypeVar

from astrbot.core.utils.event_id import new_event_id

from .message import Message
from .response import AgentResponse

TEvent = TypeVar("TEvent")


class AgentEventStream(Generic[TEvent]):
    """Expose nested async operations through one backpressured response stream.

    The producer resumes only after the consumer requests the next response.
    Closing the stream cancels pending work before acknowledging another event.
    """

    def __init__(self) -> None:
        self.active = False
        self._queue: asyncio.Queue[tuple[TEvent, asyncio.Future[None]]] = asyncio.Queue(
            maxsize=1
        )

    async def emit(self, response: TEvent) -> None:
        """Wait until the host has handled a response.

        Args:
            response: Runtime or durable event to deliver to the host.
        """
        if not self.active:
            raise asyncio.CancelledError
        acknowledged = asyncio.get_running_loop().create_future()
        await self._queue.put((response, acknowledged))
        await acknowledged

    async def run(
        self, source: AsyncGenerator[TEvent, None]
    ) -> AsyncGenerator[TEvent, None]:
        """Drive one step and join its producer even when consumption stops early.

        Args:
            source: The runner's step implementation.

        Yields:
            Responses in execution order, one at a time.
        """
        if self.active:
            raise RuntimeError("A runner step is already being consumed")
        self.active = True

        async def produce() -> None:
            try:
                async for response in source:
                    await self.emit(response)
            finally:
                await source.aclose()

        producer = asyncio.create_task(produce())
        receiving = None
        try:
            while True:
                receiving = asyncio.create_task(self._queue.get())
                done, _ = await asyncio.wait(
                    {producer, receiving}, return_when=asyncio.FIRST_COMPLETED
                )
                if receiving in done:
                    response, acknowledged = receiving.result()
                    yield response
                    if not acknowledged.done():
                        acknowledged.set_result(None)
                else:
                    await producer
                    break
        finally:
            self.active = False
            if receiving is not None:
                receiving.cancel()
            producer.cancel()
            await asyncio.gather(
                producer,
                *([receiving] if receiving is not None else []),
                return_exceptions=True,
            )
            while not self._queue.empty():
                _, acknowledged = self._queue.get_nowait()
                acknowledged.cancel()


def request_context_for_journal(
    contexts, *, source_contexts, modalities, extra_user_content_parts=None
) -> dict:
    """Capture the context at the provider boundary without temporary content.

    Args:
        contexts: The prepared messages passed to the provider.
        source_contexts: Messages before modality conversion, with private flags intact.
        modalities: Modalities supported by the selected provider.
        extra_user_content_parts: Additional content passed to the provider.

    Returns:
        Detached provider arguments and whether all their content was retained.
    """
    from astrbot.core.provider.modalities import sanitize_contexts_by_modalities

    filtered = []
    complete = True
    for message in source_contexts:
        if message.get("_no_save") if isinstance(message, dict) else message._no_save:
            complete = False
            continue
        content = (
            message.get("content") if isinstance(message, dict) else message.content
        )
        if isinstance(content, list):
            kept = [
                part
                for part in content
                if not (
                    part.get("_no_save")
                    if isinstance(part, dict)
                    else getattr(part, "_no_save", False)
                )
            ]
            if len(kept) != len(content):
                complete = False
                data = message if isinstance(message, dict) else message.model_dump()
                message = {
                    **data,
                    "content": [
                        part if isinstance(part, dict) else part.model_dump()
                        for part in kept
                    ],
                }
        filtered.append(message)

    # Modality conversion can drop private flags or turn a tool result into text.
    # When redacting, convert the safe source again instead of trusting the wire copy.
    if not complete:
        contexts = (
            sanitize_contexts_by_modalities(filtered, modalities)[0]
            if modalities
            else filtered
        )
    extra = []
    for part in extra_user_content_parts or ():
        if part.get("_no_save") if isinstance(part, dict) else part._no_save:
            complete = False
        else:
            extra.append(part if isinstance(part, dict) else part.model_dump())
    return deepcopy(
        {
            "contexts": [
                message.model_dump() if isinstance(message, Message) else message
                for message in contexts
            ],
            "extra_user_content_parts": extra,
            "complete": complete,
        }
    )


class RequestEventRecorder:
    """Pair provider attempts while attaching final usage after response decoding."""

    def __init__(
        self,
        emit: Callable[[AgentResponse], Awaitable[object]],
        payload: dict,
        *,
        invocation_id: str | None = None,
    ):
        """Attach an explicit runtime sink to one provider invocation.

        Args:
            emit: Awaited delivery of events to the runner's consumer.
            payload: Request metadata and optional filtered provider context.
            invocation_id: Parent runtime call identity shared by all retry attempts.
        """
        self.emit = emit
        self.payload = payload
        self.invocation_id = invocation_id or new_event_id()
        self.attempt = 0
        self.current_id = None
        self.network_attempt_seen = False

    async def begin(self):
        """Start an attempt, retaining its ID until settlement."""
        self.current_id = new_event_id()
        self.attempt += 1
        payload = {
            **self.payload,
            "invocation_id": self.invocation_id,
            "attempt": self.attempt,
        }
        await self.emit(AgentResponse("request.started", payload, self.current_id))

    async def before_network_attempt(self):
        """Open another attempt when the shared provider retry loop retries."""
        if self.network_attempt_seen and self.current_id is None:
            await self.begin()
        self.network_attempt_seen = True

    async def finish(self, status, *, usage=None, error_code=None):
        """Settle one attempt once.

        Args:
            status: Terminal request status.
            usage: Optional normalized token usage from the decoded response.
            error_code: Optional exception class or stable failure code.
        """
        if self.current_id is None:
            return
        payload = {"request_id": self.current_id, "status": status}
        if usage is not None:
            payload["usage"] = {
                "input_tokens": usage.input,
                "cached_input_tokens": usage.input_cached,
                "output_tokens": usage.output,
            }
        if error_code:
            payload["error"] = {"code": error_code}
        await self.emit(AgentResponse("request.finished", payload, new_event_id()))
        self.current_id = None
