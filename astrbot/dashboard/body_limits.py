"""ASGI request-body limits for Dashboard endpoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse

from astrbot.dashboard.responses import error

JSON_LIMIT = 2 * 1024 * 1024
DEFAULT_MULTIPART_LIMIT = 128 * 1024 * 1024
CONFIG_FILE_LIMIT = 500 * 1024 * 1024
BACKUP_DIRECT_LIMIT = 128 * 1024 * 1024
BACKUP_CHUNK_REQUEST_LIMIT = 2 * 1024 * 1024


class RequestBodyTooLarge(ValueError):
    """Raised when a streamed request body exceeds its endpoint limit."""


def resolve_body_limit(path: str, content_type: str | None) -> int:
    """Return the request-body limit for a Dashboard path.

    Args:
        path: ASGI request path.
        content_type: Request Content-Type header.

    Returns:
        Maximum accepted bytes.
    """
    normalized = path.rstrip("/")
    if normalized.endswith("/backups/upload/chunk") or normalized.endswith(
        "/backup/upload/chunk"
    ):
        return BACKUP_CHUNK_REQUEST_LIMIT
    if normalized.endswith("/backups/upload") or normalized.endswith("/backup/upload"):
        return BACKUP_DIRECT_LIMIT
    if (
        "/config/" in normalized
        and normalized.endswith("/file/upload")
        or normalized.endswith("/plugins/config-files")
        or "/config-files/" in normalized
    ):
        return CONFIG_FILE_LIMIT
    if content_type and "application/json" in content_type.lower():
        return JSON_LIMIT
    return DEFAULT_MULTIPART_LIMIT


class RequestBodyLimitMiddleware:
    """Reject declared and streamed ASGI request bodies above a fixed limit."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Apply the body limit to one ASGI request.

        Args:
            scope: ASGI connection scope.
            receive: Downstream request receiver.
            send: Downstream response sender.
        """
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.lower(): value
            for key, value in scope.get("headers", [])
            if isinstance(key, bytes) and isinstance(value, bytes)
        }
        content_type = headers.get(b"content-type", b"").decode(
            "latin-1", errors="ignore"
        )
        limit = resolve_body_limit(str(scope.get("path") or ""), content_type)
        declared = headers.get(b"content-length")
        if declared:
            try:
                if int(declared) > limit:
                    await self._reject(scope, receive, send, limit)
                    return
            except ValueError:
                pass

        consumed = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal consumed
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                consumed += len(body) if isinstance(body, bytes) else 0
                if consumed > limit:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await self._reject(scope, receive, send, limit)

    @staticmethod
    async def _reject(
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
        limit: int,
    ) -> None:
        response = JSONResponse(
            error(f"Request body exceeds the {limit}-byte limit"),
            status_code=413,
        )
        await response(scope, receive, send)
