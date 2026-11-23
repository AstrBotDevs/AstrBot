"""JSON request parsing shared by dashboard and platform HTTP adapters."""

from typing import Any

from starlette.requests import Request


async def read_request_json(request: Request, silent: bool = False) -> Any:
    """Read JSON, suppressing parsing failures only when explicitly requested."""
    try:
        return await request.json()
    except Exception:
        if silent:
            return None
        raise
