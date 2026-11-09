"""Storage-independent runner events and acknowledged delivery."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Generic, TypeVar

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
