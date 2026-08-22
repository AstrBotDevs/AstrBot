"""Transaction-scope helpers for store mixins."""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession


async def run_in_tx[TxResult](
    store,
    fn: Callable[[AsyncSession], Awaitable[TxResult]],
) -> TxResult:
    """Run ``fn`` inside one database session transaction.

    Args:
        store: Object exposing ``get_db()``.
        fn: Coroutine that receives the open session.

    Returns:
        The value returned by ``fn``.
    """
    async with store.get_db() as session:
        async with session.begin():
            return await fn(session)
