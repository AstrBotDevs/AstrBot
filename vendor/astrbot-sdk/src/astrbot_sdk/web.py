"""Web routes: HTTP endpoints served through the capability pipeline.

Plugins register routes with ``ctx.web.route``; the Host dashboard matches
incoming HTTP requests and replays them to the plugin as WebRequestInfo
plus an optional body pull channel. Responses are a WebResponseInfo
followed by a backpressure-controlled chunk stream, so streaming
responses (SSE, large files) work without special cases.

The contract is framework-neutral by design. Handlers may also return
starlette response objects (Response/JSONResponse/StreamingResponse/
FileResponse); they are recognized structurally, without the SDK
importing starlette itself.
"""

from __future__ import annotations

import asyncio
import inspect
import json as json_module
import mimetypes
import re
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import InvalidPluginDefinition
from .protocol_registry import register_protocol_dataclass

_WEB_CAPABILITY = "web.route"

# Bodies at or below this size travel inline in the request DTO; larger
# bodies are pulled by the plugin through the read_body channel.
INLINE_BODY_LIMIT = 4 * 1024 * 1024


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class WebRequestInfo:
    """One incoming HTTP request, replayed to the plugin."""

    route: str
    method: str
    path: str
    path_params: Mapping[str, str]
    query: tuple[tuple[str, str], ...]
    headers: Mapping[str, str]
    body: bytes | None
    body_size: int
    body_token: str | None
    username: str | None
    client_host: str | None = None


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class WebResponseInfo:
    """Response head; the body follows as stream chunks."""

    status: int
    headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class WebRouteRegistration:
    """One registered route."""

    route: str
    methods: tuple[str, ...]
    description: str
    handler: Callable[..., Any]


class WebRequest:
    """Request facade handed to route handlers."""

    def __init__(self, info: WebRequestInfo, ctx: Any) -> None:
        self._info = info
        self._ctx = ctx
        self.method = info.method
        self.path = info.path
        self.path_params = dict(info.path_params)
        self.headers = dict(info.headers)
        self.username = info.username
        self.client_host = info.client_host
        self.query = _QueryMultiDict(info.query)
        self._body_cache: bytes | None = None

    async def body(self) -> bytes:
        """Read the full request body, pulling it when not inline."""
        if self._body_cache is not None:
            return self._body_cache
        info = self._info
        if info.body is not None:
            self._body_cache = info.body
            return self._body_cache
        if info.body_token is None:
            self._body_cache = b""
            return self._body_cache
        parts = []
        async for chunk in self.stream():
            parts.append(chunk)
        self._body_cache = b"".join(parts)
        return self._body_cache

    async def stream(self) -> AsyncIterator[bytes]:
        """Iterate the request body in chunks."""
        info = self._info
        if info.body is not None:
            yield info.body
            return
        if info.body_token is None:
            return
        offset = 0
        while True:
            result = await self._ctx._invoke_capability(
                _WEB_CAPABILITY,
                "read_body",
                {"token": info.body_token, "offset": offset},
            )
            chunk = result.get("chunk") or b""
            if chunk:
                yield chunk
                offset += len(chunk)
            if result.get("done", True):
                return

    async def text(self, encoding: str = "utf-8") -> str:
        """Read the body as text."""
        return (await self.body()).decode(encoding, errors="replace")

    async def json(self) -> Any:
        """Parse the body as JSON, or None when empty/invalid."""
        raw = await self.body()
        if not raw:
            return None
        try:
            return json_module.loads(raw)
        except json_module.JSONDecodeError:
            return None


class _QueryMultiDict:
    """Minimal multi-value query mapping (last value wins on get)."""

    def __init__(self, pairs: tuple[tuple[str, str], ...]) -> None:
        self._pairs = list(pairs)

    def get(self, key: str, default: Any = None, type: Callable | None = None) -> Any:
        for item_key, item_value in reversed(self._pairs):
            if item_key != key:
                continue
            if type is None:
                return item_value
            try:
                return type(item_value)
            except (TypeError, ValueError):
                return default
        return default

    def getlist(self, key: str) -> list[str]:
        return [value for item_key, value in self._pairs if item_key == key]

    def __contains__(self, key: str) -> bool:
        return any(item_key == key for item_key, _ in self._pairs)

    def __getitem__(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value


class WebResponse:
    """Buffered response returned by route handlers."""

    def __init__(
        self,
        body: bytes | str = b"",
        status: int = 200,
        headers: Mapping[str, str] | None = None,
        content_type: str | None = None,
        _stream: Any = None,
    ) -> None:
        self.body = body.encode() if isinstance(body, str) else body
        self.status = status
        self.headers = dict(headers or {})
        if content_type is not None:
            self.headers.setdefault("content-type", content_type)
        self._stream = _stream

    @classmethod
    def json(cls, data: Any, status: int = 200) -> WebResponse:
        """Build a JSON response."""
        return cls(
            json_module.dumps(data, ensure_ascii=False).encode(),
            status=status,
            content_type="application/json",
        )

    @classmethod
    def text(cls, text: str, status: int = 200) -> WebResponse:
        """Build a plain-text response."""
        return cls(text, status=status, content_type="text/plain; charset=utf-8")

    @classmethod
    def redirect(cls, url: str, status: int = 302) -> WebResponse:
        """Build a redirect response."""
        return cls(b"", status=status, headers={"location": url})

    def _with_headers(self, headers: Mapping[str, str] | None) -> WebResponse:
        if headers:
            merged = dict(self.headers)
            merged.update(headers)
            self.headers = merged
        return self

    def _normalize(self) -> tuple[WebResponseInfo, AsyncIterator[bytes]]:
        """Convert to the wire shape: response info plus a chunk stream."""
        info = WebResponseInfo(status=self.status, headers=self.headers)
        if self._stream is not None:
            stream = self._stream

            async def chunks() -> AsyncIterator[bytes]:
                async for chunk in stream:
                    yield chunk.encode() if isinstance(chunk, str) else bytes(chunk)

            return info, chunks()

        async def buffered() -> AsyncIterator[bytes]:
            if self.body:
                yield self.body

        return info, buffered()


def json_response(
    data: Any = None,
    *,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> WebResponse:
    """Build a JSON response (mirrors astrbot.api.web.json_response)."""
    return WebResponse.json(
        {} if data is None else data,
        status=status_code,
    )._with_headers(headers)


def error_response(
    message: str,
    *,
    status_code: int = 400,
    data: Any = None,
    headers: Mapping[str, str] | None = None,
) -> WebResponse:
    """Build a standard error envelope (mirrors api.web.error_response)."""
    return json_response(
        {"status": "error", "message": message, "data": data},
        status_code=status_code,
        headers=headers,
    )


def file_response(
    path: str | Path,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> WebResponse:
    """Build a file download response, streamed in chunks."""
    file_path = Path(path)
    media_type = (
        content_type
        or mimetypes.guess_type(str(filename or file_path.name))[0]
        or "application/octet-stream"
    )
    response_headers: dict[str, str] = dict(headers or {})
    if filename is not None:
        response_headers.setdefault(
            "content-disposition",
            f'attachment; filename="{filename}"',
        )

    async def chunks() -> AsyncIterator[bytes]:
        file = await asyncio.to_thread(file_path.open, "rb")
        try:
            while chunk := await asyncio.to_thread(file.read, 512 * 1024):
                yield chunk
        finally:
            await asyncio.to_thread(file.close)

    return WebResponse(
        status=200,
        headers=response_headers,
        content_type=media_type,
        _stream=chunks(),
    )


def stream_response(
    content: Any,
    *,
    content_type: str = "text/event-stream",
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> WebResponse:
    """Build a streaming response from a sync or async iterable."""
    if hasattr(content, "__aiter__"):
        stream = content
    else:

        async def iterate() -> AsyncIterator[Any]:
            for item in content:
                yield item

        stream = iterate()
    return WebResponse(
        status=status_code,
        headers=headers,
        content_type=content_type,
        _stream=stream,
    )


def _looks_like_starlette_response(result: Any) -> bool:
    """Duck-typed starlette Response check (no starlette import)."""
    return (
        hasattr(result, "status_code")
        and hasattr(result, "headers")
        and (
            hasattr(result, "body")
            or hasattr(result, "body_iterator")
            or hasattr(result, "path")
        )
    )


async def _normalize_starlette_like(
    result: Any,
) -> tuple[WebResponseInfo, AsyncIterator[bytes]]:
    """Normalize a starlette-shaped response without importing starlette."""
    headers = {str(k).lower(): str(v) for k, v in result.headers.items()}
    info = WebResponseInfo(status=int(result.status_code), headers=headers)

    path = getattr(result, "path", None)
    if path is not None:
        return file_response(path)._normalize()

    body_iterator = getattr(result, "body_iterator", None)
    if body_iterator is not None:

        async def streaming() -> AsyncIterator[bytes]:
            async for chunk in body_iterator:
                yield chunk.encode() if isinstance(chunk, str) else bytes(chunk)

        return info, streaming()

    body = result.body
    if isinstance(body, str):
        body = body.encode()

    async def buffered() -> AsyncIterator[bytes]:
        if body:
            yield bytes(body)

    return info, buffered()


async def normalize_web_result(
    result: Any,
) -> tuple[WebResponseInfo, AsyncIterator[bytes]]:
    """Normalize one handler result into response info plus a chunk stream."""
    if isinstance(result, WebResponse):
        return result._normalize()
    if _looks_like_starlette_response(result):
        return await _normalize_starlette_like(result)
    if isinstance(result, dict | list):
        return await normalize_web_result(WebResponse.json(result))
    if isinstance(result, str | bytes):
        return await normalize_web_result(WebResponse(result))
    if isinstance(result, tuple) and len(result) in (2, 3):
        body, status = result[0], result[1]
        headers = result[2] if len(result) == 3 else None
        normalized, chunks = await normalize_web_result(body)
        info = WebResponseInfo(
            status=status,
            headers=headers or normalized.headers,
        )

        async def replay() -> AsyncIterator[bytes]:
            async for chunk in chunks:
                yield chunk

        return info, replay()
    if inspect.isasyncgen(result) or (
        inspect.isgenerator(result) or hasattr(result, "__aiter__")
    ):
        info = WebResponseInfo(status=200, headers={})

        async def streaming() -> AsyncIterator[bytes]:
            async for chunk in result:
                if isinstance(chunk, str):
                    yield chunk.encode()
                elif isinstance(chunk, bytes | bytearray):
                    yield bytes(chunk)
                else:
                    yield json_module.dumps(chunk, ensure_ascii=False).encode()

        return info, streaming()
    if result is None:

        async def no_content() -> AsyncIterator[bytes]:
            return
            yield b""

        return WebResponseInfo(status=204, headers={}), no_content()
    raise TypeError(f"unsupported web handler result: {type(result)!r}")


class WebService:
    """Register plugin web routes (``ctx.web``)."""

    _ROUTE_PARAM_RE = re.compile(r"<(?:(path):)?([A-Za-z_][A-Za-z0-9_]*)>")

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx
        self.routes: list[WebRouteRegistration] = []

    def _validate_route(self, path: str) -> None:
        """Validate the `<name>` / `<path:name>` route pattern syntax."""
        for match in self._ROUTE_PARAM_RE.finditer(path):
            if match.group(1) == "path" and match.end() != len(path):
                raise InvalidPluginDefinition(
                    f"<path:...> parameter must be the last segment: {path}"
                )
        stripped = self._ROUTE_PARAM_RE.sub("", path)
        if any(char in stripped for char in "<>{}"):
            raise InvalidPluginDefinition(
                f"malformed route parameter in {path!r}; "
                "use <name> or <path:name> segments"
            )

    def route(
        self,
        path: str,
        methods: tuple[str, ...] | list[str] = ("GET",),
        description: str = "",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register one HTTP route served through the pipeline.

        Paths use the dashboard route syntax: `<name>` matches one path
        segment and `<path:name>` matches the remaining multi-segment path.
        """
        if not path.startswith("/"):
            raise ValueError("web route paths must start with '/'")
        self._validate_route(path)

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            self.routes.append(
                WebRouteRegistration(
                    route=path,
                    methods=tuple(method.upper() for method in methods),
                    description=description,
                    handler=handler,
                ),
            )
            return handler

        return decorator
