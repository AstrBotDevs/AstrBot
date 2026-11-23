"""Cancellation-safe delivery for platform queues with explicit close signals."""

import asyncio
from collections.abc import Awaitable, Callable


def discard_finished_listener(
    listeners: dict[str, asyncio.Task], key: str, finished: asyncio.Task
) -> None:
    """Unregister only this task, preserving a listener created under the same key."""
    if listeners.get(key) is finished:
        listeners.pop(key)


async def listen_to_queue[T](
    queue: asyncio.Queue[T],
    close_event: asyncio.Event,
    callback_getter: Callable[[], Callable[[T], Awaitable[None]] | None],
    on_callback_error: Callable[[Exception], None],
) -> None:
    """Deliver available items until closure, draining every spawned wait task.

    Closure wins if both waiters complete together. The callback is looked up
    for every item so listeners can be replaced while a queue remains open.
    """
    while True:
        get_task = asyncio.create_task(queue.get())
        close_task = asyncio.create_task(close_event.wait())
        try:
            done, pending = await asyncio.wait(
                {get_task, close_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if close_task in done:
                break
            data = get_task.result()
            callback = callback_getter()
            if callback is not None:
                try:
                    await callback(data)
                except Exception as error:
                    on_callback_error(error)
        except asyncio.CancelledError:
            break
        finally:
            for task in (get_task, close_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(get_task, close_task, return_exceptions=True)
