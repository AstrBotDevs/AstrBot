"""Storage-independent runner events and acknowledged delivery."""

import asyncio
import inspect
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable

from .response import AgentResponse


class AgentEventStream:
    """Expose nested async operations through one backpressured response stream.

    The producer resumes only after the consumer requests the next response.
    Closing the stream cancels pending work before acknowledging another event.
    """

    def __init__(self):
        self.active = False
        self._queue: asyncio.Queue[tuple[AgentResponse, asyncio.Future[None]]] = (
            asyncio.Queue(maxsize=1)
        )

    async def emit(self, response: AgentResponse) -> None:
        """Wait until the host has handled a response.

        Args:
            response: Runtime or durable event to deliver to the host.
        """
        if not self.active:
            raise asyncio.CancelledError
        acknowledged = asyncio.get_running_loop().create_future()
        await self._queue.put((response, acknowledged))
        await acknowledged

    async def run(self, source: AsyncGenerator[AgentResponse, None]):
        """Drive one step and join its producer even when consumption stops early.

        Args:
            source: The runner's step implementation.

        Yields:
            Responses in execution order, one at a time.
        """
        if self.active:
            raise RuntimeError("A runner step is already being consumed")
        self.active = True

        async def produce():
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


def request_recorder_kwargs(call: Callable, recorder) -> dict:
    """Pass instrumentation only to adapters that explicitly accept it.

    Args:
        call: Provider method, which may be implemented by an older plugin.
        recorder: Optional request attempt recorder.

    Returns:
        Local instrumentation arguments, never arbitrary model request kwargs.
    """
    if (
        recorder is not None
        and "request_event_recorder" in inspect.signature(call).parameters
    ):
        return {"request_event_recorder": recorder}
    return {}


class RequestEventRecorder:
    """Pair provider attempts while attaching final usage after response decoding."""

    def __init__(
        self, emit: Callable[[AgentResponse], Awaitable[object]], payload: dict
    ):
        """Attach an explicit runtime sink to one provider invocation.

        Args:
            emit: Awaited delivery of events to the runner's consumer.
            payload: Request metadata, excluding the model request body.
        """
        self.emit = emit
        self.payload = payload
        self.current_id = None
        self.network_attempt_seen = False

    async def begin(self):
        """Start an attempt, retaining its ID until settlement."""
        self.current_id = str(uuid.uuid4())
        await self.emit(AgentResponse("request.started", self.payload, self.current_id))

    async def before_network_attempt(self):
        """Open another attempt when the shared provider retry loop retries."""
        if self.network_attempt_seen and self.current_id is None:
            await self.begin()
        self.network_attempt_seen = True

    async def finish(self, status, *, usage=None, error_code=None):
        """Settle one attempt once without storing its request body.

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
        await self.emit(AgentResponse("request.finished", payload, str(uuid.uuid4())))
        self.current_id = None
