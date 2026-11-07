import asyncio
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import TypeVar, cast

T = TypeVar("T")


async def iterate_in_task(
    generator: AsyncGenerator[T, None],
) -> AsyncGenerator[T, None]:
    """Advance and close a generator in one task, only when a caller requests it.

    Args:
        generator: Generator owned by this iterator until completion or close.

    Yields:
        The original generator's values without prefetching.

    Raises:
        BaseException: Original iteration or cleanup failures.
    """
    advance = asyncio.Event()
    results: asyncio.Queue[tuple[bool, T | BaseException]] = asyncio.Queue(maxsize=1)
    finishing = False
    stop_requested = False
    terminal: BaseException | None = None

    async def produce() -> None:
        nonlocal finishing, terminal
        try:
            while True:
                await advance.wait()
                advance.clear()
                try:
                    value = await anext(generator)
                except asyncio.CancelledError as error:
                    if not stop_requested:
                        terminal = error
                    break
                except BaseException as error:
                    terminal = error
                    break
                if stop_requested:
                    return
                await results.put((True, value))
        finally:
            finishing = True
            try:
                await generator.aclose()
            except BaseException as error:
                terminal = error
        if terminal is not None:
            # Closing consumers may leave a value queued; terminal is also read below.
            with suppress(asyncio.QueueFull):
                results.put_nowait((False, terminal))

    owner = asyncio.create_task(produce())
    try:
        while True:
            advance.set()
            succeeded, value = await results.get()
            if not succeeded:
                if isinstance(value, StopAsyncIteration):
                    return
                raise cast(BaseException, value)
            yield cast(T, value)
    finally:
        interrupted = False
        if not finishing:
            stop_requested = True
            owner.cancel()
        while not owner.done():
            try:
                await asyncio.shield(owner)
            except asyncio.CancelledError:
                if not owner.done():
                    interrupted = True
        with suppress(asyncio.CancelledError):
            await owner
        if (
            not interrupted
            and terminal is not None
            and not isinstance(terminal, StopAsyncIteration)
        ):
            raise cast(BaseException, terminal)
        if not interrupted and not results.empty():
            succeeded, value = results.get_nowait()
            if not succeeded and not isinstance(value, StopAsyncIteration):
                raise cast(BaseException, value)
        if interrupted:
            raise asyncio.CancelledError
