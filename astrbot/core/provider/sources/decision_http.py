"""HTTP transport setup for decision provider adapters."""

import asyncio

import httpx


def create_decision_transport(
    max_concurrency: int,
    *,
    timeout: float,
    proxy: str | None,
    transport: httpx.AsyncBaseTransport | None,
    headers: httpx.Headers | dict[str, str],
) -> tuple[asyncio.Semaphore, httpx.AsyncClient]:
    """Validate concurrency before allocating a semaphore and HTTP client."""
    if max_concurrency <= 0:
        raise ValueError("max_concurrency must be greater than 0")
    semaphore = asyncio.Semaphore(max_concurrency)
    client = httpx.AsyncClient(
        timeout=timeout, proxy=proxy, transport=transport, headers=headers
    )
    return semaphore, client
