import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from astrbot.core.utils.network_utils import create_proxy_client

_MOONSHOT_TIMEOUT_SECONDS = 600.0
_MAX_RETRIES = 2
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})


async def _request_with_retry(
    send_request: Callable[[], Awaitable[httpx.Response]],
) -> httpx.Response:
    """Execute an HTTP request with OpenAI-compatible transient retry behavior.

    Args:
        send_request: Zero-argument coroutine factory executing one HTTP attempt.

    Returns:
        Successful HTTP response after passing ``raise_for_status()``.
    """
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = await send_request()
        except httpx.TransportError:
            if attempt >= _MAX_RETRIES:
                raise
        else:
            if (
                response.status_code not in _RETRYABLE_STATUS_CODES
                and response.status_code < 500
            ) or attempt >= _MAX_RETRIES:
                response.raise_for_status()
                return response
        await asyncio.sleep(0.5 * (2**attempt))
    raise RuntimeError("Unreachable retry state")


async def extract_file_moonshotai(file_path: str, api_key: str) -> str:
    """Extract text from a file using Moonshot AI API.

    Args:
        file_path: Path to the local file to extract text from.
        api_key: Moonshot AI API key.

    Returns:
        Extracted text content from the file.
    """
    path = Path(file_path)
    async with create_proxy_client(
        "Moonshot",
        headers={"Authorization": f"Bearer {api_key}"},
    ) as client:

        async def _upload() -> httpx.Response:
            with path.open("rb") as file_handle:
                return await client.post(
                    "https://api.moonshot.cn/v1/files",
                    data={"purpose": "file-extract"},
                    files={"file": (path.name, file_handle)},
                    timeout=_MOONSHOT_TIMEOUT_SECONDS,
                )

        upload_resp = await _request_with_retry(_upload)
        file_id = upload_resp.json()["id"]

        content_resp = await _request_with_retry(
            lambda: client.get(
                f"https://api.moonshot.cn/v1/files/{file_id}/content",
                timeout=_MOONSHOT_TIMEOUT_SECONDS,
            )
        )
        return content_resp.text
