"""Exactly-once stream lifecycle coordination for Agent responses."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class StreamSignal(StrEnum):
    """User-visible stream lifecycle signals."""

    START = "START"
    DELTA = "DELTA"
    HEARTBEAT = "HEARTBEAT"
    TOOL_STATUS = "TOOL_STATUS"
    END = "END"
    ERROR = "ERROR"
    CANCEL = "CANCEL"


@dataclass(slots=True)
class StreamFrame:
    """One normalized stream frame."""

    signal: StreamSignal
    payload: Any | None = None
    timestamp: float = 0.0


class StreamController:
    """Bound a stream, emit heartbeats, and guarantee one terminal frame."""

    def __init__(self, *, idle_timeout: float = 15.0) -> None:
        self.idle_timeout = max(0.01, float(idle_timeout))
        self._terminal = False

    async def run(
        self,
        source: AsyncIterator[Any],
        *,
        send: Callable[[StreamFrame], Awaitable[None]] | None = None,
    ) -> AsyncIterator[StreamFrame]:
        """Consume a provider stream under a heartbeat watchdog.

        Args:
            source: Async iterator producing provider deltas.
            send: Optional callback receiving each normalized frame.

        Yields:
            START, DELTA, HEARTBEAT and exactly one terminal frame.
        """

        # A controller may be reused by a platform adapter for another stream;
        # each invocation owns an independent terminal lifecycle.
        self._terminal = False
        last_activity = time.monotonic()

        async def emit(frame: StreamFrame) -> None:
            nonlocal last_activity
            last_activity = time.monotonic()
            if send is not None:
                await send(frame)

        start = StreamFrame(StreamSignal.START, timestamp=time.time())
        await emit(start)
        yield start
        iterator = source.__aiter__()
        next_task: asyncio.Task[Any] | None = None
        try:
            while True:
                if next_task is None:
                    next_task = asyncio.create_task(anext(iterator))
                done, _ = await asyncio.wait({next_task}, timeout=self.idle_timeout)
                if not done:
                    heartbeat = StreamFrame(
                        StreamSignal.HEARTBEAT, timestamp=time.time()
                    )
                    await emit(heartbeat)
                    yield heartbeat
                    continue
                try:
                    item = next_task.result()
                except StopAsyncIteration:
                    break
                finally:
                    next_task = None
                frame = StreamFrame(StreamSignal.DELTA, item, time.time())
                await emit(frame)
                yield frame
                if time.monotonic() - last_activity > self.idle_timeout:
                    break
            terminal = StreamFrame(StreamSignal.END, timestamp=time.time())
            self._terminal = True
            await emit(terminal)
            yield terminal
        except asyncio.CancelledError:
            if not self._terminal:
                terminal = StreamFrame(StreamSignal.CANCEL, timestamp=time.time())
                self._terminal = True
                await emit(terminal)
                yield terminal
            raise
        except Exception as exc:  # noqa: BLE001
            if not self._terminal:
                terminal = StreamFrame(StreamSignal.ERROR, exc, time.time())
                self._terminal = True
                await emit(terminal)
                yield terminal
        finally:
            if next_task is not None and not next_task.done():
                next_task.cancel()
            if next_task is not None:
                # Await the cancelled producer so a provider does not leak a
                # pending task into the next Agent turn or process shutdown.
                try:
                    await next_task
                except (asyncio.CancelledError, StopAsyncIteration):
                    pass
                except Exception:
                    # The terminal ERROR/CANCEL frame has already been emitted;
                    # producer cleanup must not create a second user response.
                    pass
