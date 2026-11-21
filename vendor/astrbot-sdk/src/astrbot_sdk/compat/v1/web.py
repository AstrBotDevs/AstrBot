"""Legacy web API compat: replay dashboard requests in a real Quart context.

Legacy register_web_api handlers run against the framework they were
written for: the Runner builds a real Quart request context from the
relayed WebRequestInfo (quart is available through the core environment),
binds the dashboard username on g, and invokes the handler. Responses are
normalized into the info + chunk-stream convention, including starlette
responses, Quart responses, plain values and async generators.
"""

from __future__ import annotations

import contextvars
import inspect
import json as json_module
from collections.abc import AsyncIterator, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode

from ...web import WebRequestInfo, WebResponseInfo


class WebRouteEntry:
    """One legacy register_web_api registration."""

    def __init__(self, route: str, methods: list[str], desc: str, handler: Any) -> None:
        self.route = route
        self.methods = [method.upper() for method in methods]
        self.desc = desc
        self.handler = handler


_quart_apps: dict[str, Any] = {}


def _quart_app(plugin_name: str) -> Any:
    app = _quart_apps.get(plugin_name)
    if app is None:
        from quart import Quart

        app = Quart(f"astrbot_plugin_{plugin_name}")
        app.json.sort_keys = False
        _quart_apps[plugin_name] = app
    return app


async def _read_request_body(ctx: Any, request: WebRequestInfo) -> bytes:
    """Read the full request body, pulling large bodies from the Host."""
    if request.body is not None:
        return request.body
    if request.body_token is None:
        return b""
    parts = []
    offset = 0
    while True:
        result = await ctx._invoke_capability(
            "web.route",
            "read_body",
            {"token": request.body_token, "offset": offset},
        )
        chunk = result.get("chunk") or b""
        if chunk:
            parts.append(chunk)
            offset += len(chunk)
        if result.get("done", True):
            break
    return b"".join(parts)


async def _normalize_quart_result(
    result: Any,
    app: Any,
) -> tuple[WebResponseInfo, AsyncIterator[bytes]]:
    """Normalize one legacy handler result into info plus a chunk stream."""
    from quart import Response as QuartResponse
    from quart import jsonify

    if isinstance(result, tuple) and len(result) in (2, 3):
        body, status = result[0], result[1]
        extra_headers = result[2] if len(result) == 3 else None
        info, chunks = await _normalize_quart_result(body, app)
        headers = dict(info.headers)
        if extra_headers:
            headers.update({str(k): str(v) for k, v in extra_headers.items()})
        return WebResponseInfo(status=status, headers=headers), chunks

    if isinstance(result, dict | list):
        result = jsonify(result)

    from ...web import _looks_like_starlette_response, _normalize_starlette_like

    if _looks_like_starlette_response(result):
        return await _normalize_starlette_like(result)

    if isinstance(result, QuartResponse):
        headers = {str(k).lower(): str(v) for k, v in result.headers.items()}
        info = WebResponseInfo(status=result.status_code, headers=headers)

        async def quart_chunks() -> AsyncIterator[bytes]:
            body = result.response
            if hasattr(body, "__aiter__"):
                async for chunk in body:
                    yield chunk.encode() if isinstance(chunk, str) else bytes(chunk)
            else:
                for chunk in body:
                    yield chunk.encode() if isinstance(chunk, str) else bytes(chunk)

        return info, quart_chunks()

    if hasattr(result, "__aiter__"):
        info = WebResponseInfo(status=200, headers={})

        async def generator_chunks() -> AsyncIterator[bytes]:
            async for chunk in result:
                yield chunk.encode() if isinstance(chunk, str) else bytes(chunk)

        return info, generator_chunks()

    if result is None:

        async def empty() -> AsyncIterator[bytes]:
            return
            yield b""

        return WebResponseInfo(status=204, headers={}), empty

    body = json_module.dumps(result, ensure_ascii=False).encode()

    async def buffered() -> AsyncIterator[bytes]:
        yield body

    return (
        WebResponseInfo(status=200, headers={"content-type": "application/json"}),
        buffered(),
    )


async def invoke_web_route(
    plugin: Any,
    entry: WebRouteEntry,
    request: WebRequestInfo,
) -> AsyncIterator[dict]:
    """Replay one relayed request against a legacy route registration."""
    from quart import g as quart_g

    sdk_ctx = plugin.context._inner
    body = await _read_request_body(sdk_ctx, request)
    query_string = urlencode(list(request.query))
    path = request.path + (f"?{query_string}" if query_string else "")

    plugin_name = getattr(plugin, "name", None) or "legacy"
    app = _quart_app(plugin_name)
    async with app.test_request_context(
        path,
        method=request.method,
        headers={str(k): str(v) for k, v in request.headers.items()},
        data=body,
    ):
        quart_g.username = request.username
        _bind_api_web_request(request, body)
        try:
            outcome = entry.handler(**dict(request.path_params))
            result = await outcome if inspect.isawaitable(outcome) else outcome
        except Exception as exc:
            # quart.abort() raises a werkzeug HTTPException; translate it
            # into the corresponding HTTP response instead of a 500.
            from werkzeug.exceptions import HTTPException

            if not isinstance(exc, HTTPException):
                raise
            description = exc.description or exc.name
            info = WebResponseInfo(
                status=exc.code or 500,
                headers={"content-type": "text/plain; charset=utf-8"},
            )

            async def aborted() -> AsyncIterator[bytes]:
                yield str(description).encode()

            yield {"info": info}
            async for chunk in aborted():
                yield {"chunk": chunk}
            return
        info, chunks = await _normalize_quart_result(result, app)
        yield {"info": info}
        async for chunk in chunks:
            yield {"chunk": chunk}


# ---- astrbot.api.web facade -------------------------------------------------

_API_WEB_REQUEST_VAR: contextvars.ContextVar = contextvars.ContextVar(
    "api_web_request",
)


def _bind_api_web_request(request: WebRequestInfo, body: bytes) -> None:
    """Bind the facade request for the current invocation."""
    _API_WEB_REQUEST_VAR.set((request, body))


def bind_request_context(request: Any, body: bytes = b""):
    """Bind a plugin Web request for the current async context.

    Legacy parity for astrbot.api.web.bind_request_context; mostly used by
    plugin tests that drive handlers outside a real request.
    """
    import contextlib

    @contextlib.contextmanager
    def _bound():
        token = _API_WEB_REQUEST_VAR.set((request, body))
        try:
            yield request
        finally:
            _API_WEB_REQUEST_VAR.reset(token)

    return _bound()


def _current_api_web_request() -> tuple[WebRequestInfo, bytes]:
    try:
        return _API_WEB_REQUEST_VAR.get()
    except LookupError as exc:
        raise RuntimeError(
            "astrbot.api.web.request is only available inside a Web API handler"
        ) from exc


class PluginMultiDict:
    """Legacy multi-value mapping for query and form data."""

    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        self._pairs = pairs

    def get(self, key: str, default: Any = None, type: Any = None) -> Any:
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

    def getlist(self, key: str) -> list:
        return [value for item_key, value in self._pairs if item_key == key]

    def __contains__(self, key: str) -> bool:
        return any(item_key == key for item_key, _ in self._pairs)

    def __getitem__(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def multi_items(self) -> list[tuple[str, Any]]:
        return list(self._pairs)


class PluginUploadFile:
    """Legacy uploaded file; content lives in memory inside the Runner."""

    def __init__(self, filename: str, content_type: str, content: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self) -> bytes:
        return self._content

    async def save(self, path: Any) -> None:
        import aiofiles

        async with aiofiles.open(path, "wb") as file:
            await file.write(self._content)


class ApiWebRequestProxy:
    """Facade for astrbot.api.web.request inside legacy handlers."""

    @property
    def method(self) -> str:
        return _current_api_web_request()[0].method

    @property
    def path(self) -> str:
        return _current_api_web_request()[0].path

    @property
    def path_params(self) -> dict:
        return dict(_current_api_web_request()[0].path_params)

    @property
    def headers(self) -> Mapping[str, str]:
        return _current_api_web_request()[0].headers

    @property
    def content_type(self) -> str | None:
        return _current_api_web_request()[0].headers.get("content-type")

    @property
    def username(self) -> str | None:
        return _current_api_web_request()[0].username

    @property
    def client_host(self) -> str | None:
        return _current_api_web_request()[0].client_host

    @property
    def cookies(self) -> dict:
        # Dashboard credentials never cross the boundary, so plugin-scoped
        # cookie reading degrades to an empty mapping rather than failing.
        return {}

    @property
    def query(self) -> PluginMultiDict:
        return PluginMultiDict(list(_current_api_web_request()[0].query))

    async def body(self) -> bytes:
        return _current_api_web_request()[1]

    async def json(self, default: Any = None) -> Any:
        raw = await self.body()
        if not raw:
            return default
        try:
            return json_module.loads(raw)
        except json_module.JSONDecodeError:
            return default

    async def form(self) -> PluginMultiDict:
        content_type = self.content_type or ""
        raw = await self.body()
        if "application/x-www-form-urlencoded" in content_type:
            return PluginMultiDict(parse_qsl(raw.decode("utf-8", errors="replace")))
        if "multipart/form-data" in content_type:
            fields, _ = _parse_multipart(content_type, raw)
            return PluginMultiDict(fields)
        return PluginMultiDict([])

    async def files(self) -> PluginMultiDict:
        content_type = self.content_type or ""
        if "multipart/form-data" not in content_type:
            return PluginMultiDict([])
        _, files = _parse_multipart(content_type, await self.body())
        return PluginMultiDict(files)


def json_response(
    data: Any = None,
    *,
    status_code: int = 200,
    headers: dict | None = None,
) -> Any:
    """Mirror astrbot.api.web.json_response (returns a starlette response)."""
    from fastapi.encoders import jsonable_encoder
    from starlette.responses import JSONResponse

    return JSONResponse(
        jsonable_encoder({} if data is None else data),
        status_code=status_code,
        headers=headers,
    )


def error_response(
    message: str,
    *,
    status_code: int = 400,
    data: Any = None,
    headers: dict | None = None,
) -> Any:
    """Mirror astrbot.api.web.error_response (AstrBot error envelope)."""
    return json_response(
        {"status": "error", "message": message, "data": data},
        status_code=status_code,
        headers=headers,
    )


def file_response(
    path: Any,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    headers: dict | None = None,
) -> Any:
    """Mirror astrbot.api.web.file_response (starlette FileResponse)."""
    from starlette.responses import FileResponse

    return FileResponse(
        path,
        filename=filename,
        media_type=content_type,
        headers=headers,
    )


def stream_response(
    content: Any,
    *,
    content_type: str = "text/event-stream",
    status_code: int = 200,
    headers: dict | None = None,
) -> Any:
    """Mirror astrbot.api.web.stream_response (starlette StreamingResponse)."""
    from starlette.responses import StreamingResponse

    return StreamingResponse(
        content,
        media_type=content_type,
        status_code=status_code,
        headers=headers,
    )


def _parse_multipart(content_type: str, body: bytes) -> tuple[list, list]:
    """Parse multipart/form-data into form fields and upload files."""
    import email

    message = email.message_from_bytes(
        f"Content-Type: {content_type}\r\n\r\n".encode() + body,
    )
    fields: list[tuple[str, str]] = []
    files: list[tuple[str, PluginUploadFile]] = []
    for part in message.walk():
        disposition = part.get("Content-Disposition", "")
        if "form-data" not in disposition:
            continue
        params = dict(part.get_params(header="content-disposition") or [])
        name = params.get("name")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        filename = params.get("filename")
        if filename:
            files.append(
                (
                    name,
                    PluginUploadFile(
                        filename,
                        part.get_content_type(),
                        payload,
                    ),
                ),
            )
        else:
            fields.append((name, payload.decode("utf-8", errors="replace")))
    return fields, files
