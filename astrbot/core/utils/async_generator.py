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

    async def produce() -> None:
        nonlocal finishing
        try:
            while True:
                await advance.wait()
                advance.clear()
                try:
                    value = await anext(generator)
                except BaseException as error:
                    await results.put((False, error))
                    return
                await results.put((True, value))
        finally:
            finishing = True
            await generator.aclose()

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
        if not finishing:
            owner.cancel()
        with suppress(asyncio.CancelledError):
            await owner
