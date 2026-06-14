from __future__ import annotations

import contextvars
from collections.abc import Callable, KeysView
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generic, TypeVar, overload

from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from starlette.datastructures import Headers
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.responses import StreamingResponse

ValueT = TypeVar("ValueT")
DefaultT = TypeVar("DefaultT")
ConvertedT = TypeVar("ConvertedT")


class PluginMultiDict(Generic[ValueT]):
    """Dictionary-like request values that preserves duplicate keys."""

    def __init__(self, pairs: list[tuple[str, ValueT]]) -> None:
        self._pairs = pairs

    @overload
    def get(self, key: str) -> ValueT | None: ...

    @overload
    def get(self, key: str, default: DefaultT) -> ValueT | DefaultT: ...

    @overload
    def get(
        self,
        key: str,
        default: DefaultT,
        type: Callable[[ValueT], ConvertedT],
    ) -> ConvertedT | DefaultT: ...

    def get(self, key: str, default: Any = None, type: Callable | None = None):
        """Return the last value for a key.

        Args:
            key: Value key to read.
            default: Value returned when the key is missing or conversion fails.
            type: Optional callable used to convert the value.

        Returns:
            The matching value, converted value, or default.
        """
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

    def getlist(self, key: str) -> list[ValueT]:
        """Return all values for a key.

        Args:
            key: Value key to read.

        Returns:
            Values in request order.
        """
        return [item_value for item_key, item_value in self._pairs if item_key == key]

    def keys(self) -> KeysView[str]:
        return dict.fromkeys(item_key for item_key, _ in self._pairs).keys()

    def values(self) -> list[ValueT]:
        return [self[key] for key in self.keys()]

    def items(self) -> list[tuple[str, ValueT]]:
        return [(key, self[key]) for key in self.keys()]

    def __contains__(self, key: str) -> bool:
        return any(item_key == key for item_key, _ in self._pairs)

    def __getitem__(self, key: str) -> ValueT:
        value = self.get(key)
        if value is None and key not in self:
            raise KeyError(key)
        return value

    def __bool__(self) -> bool:
        return bool(self._pairs)


class PluginUploadFile:
    """Uploaded file wrapper exposed to plugin Web API handlers."""

    def __init__(self, upload_file: StarletteUploadFile) -> None:
        self._upload_file: StarletteUploadFile = upload_file
        self.filename: str | None = upload_file.filename
        self.content_type: str | None = upload_file.content_type
        self.headers: Headers = upload_file.headers
        self.content_length: int | None = self._resolve_content_length()

    def _resolve_content_length(self) -> int | None:
        try:
            raw = self.headers.get("content-length")
            return int(raw) if raw else None
        except (TypeError, ValueError):
            return None

    async def save(self, destination: str | Path) -> None:
        """Save the uploaded file to disk.

        Args:
            destination: Destination file path.
        """
        path = Path(destination)
        try:
            await self._upload_file.seek(0)
        except Exception:
            pass
        with path.open("wb") as output:
            while True:
                chunk = await self._upload_file.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)

    async def read(self, size: int = -1) -> bytes:
        """Read bytes from the uploaded file.

        Args:
            size: Maximum number of bytes to read. Use -1 to read all bytes.

        Returns:
            File bytes.
        """
        return await self._upload_file.read(size)

    async def write(self, data: bytes) -> None:
        """Write bytes to the uploaded file object.

        Args:
            data: Bytes to write.
        """
        await self._upload_file.write(data)

    async def seek(self, offset: int) -> None:
        """Move the uploaded file cursor.

        Args:
            offset: Absolute byte offset.
        """
        await self._upload_file.seek(offset)

    async def close(self) -> None:
        """Close the uploaded file."""
        await self._upload_file.close()

    def __getattr__(self, key: str) -> Any:
        return getattr(self._upload_file, key)


class PluginRequest:
    """Request object exposed to plugin Web API handlers."""

    def __init__(
        self,
        request_: Any,
        *,
        path_params: dict[str, Any] | None = None,
        plugin_name: str | None = None,
        username: str | None = None,
    ) -> None:
        self._request: Any = request_
        self.method: str = request_.method
        self.path: str = request_.url.path
        self.headers: Headers = request_.headers
        self.cookies: dict[str, str] = request_.cookies
        self.content_type: str | None = request_.headers.get("content-type")
        self.client_host: str | None = request_.client.host if request_.client else None
        self.path_params: dict[str, Any] = path_params or {}
        self.plugin_name: str | None = plugin_name
        self.username: str | None = username
        self.query: PluginMultiDict[str] = PluginMultiDict[str](
            list(request_.query_params.multi_items())
        )
        self._form_cache: PluginMultiDict[str] | None = None
        self._files_cache: PluginMultiDict[PluginUploadFile] | None = None

    async def body(self) -> bytes:
        """Read the raw request body.

        Returns:
            Raw request body bytes.
        """
        return await self._request.body()

    async def json(self, default: DefaultT | None = None) -> Any | DefaultT | None:
        """Read the JSON request body.

        Args:
            default: Value returned when the request body cannot be parsed as JSON.

        Returns:
            Parsed JSON data or default.
        """
        try:
            return await self._request.json()
        except Exception:
            return default

    async def _load_form_parts(self) -> None:
        if self._form_cache is not None and self._files_cache is not None:
            return
        form = await self._request.form()
        form_pairs: list[tuple[str, str]] = []
        file_pairs: list[tuple[str, PluginUploadFile]] = []
        for key, value in form.multi_items():
            if isinstance(value, StarletteUploadFile):
                file_pairs.append((key, PluginUploadFile(value)))
            else:
                form_pairs.append((key, value))
        self._form_cache = PluginMultiDict(form_pairs)
        self._files_cache = PluginMultiDict(file_pairs)

    async def form(self) -> PluginMultiDict[str]:
        """Read form fields from a multipart or form-urlencoded request.

        Returns:
            Form values without uploaded files.
        """
        await self._load_form_parts()
        assert self._form_cache is not None
        return self._form_cache

    async def files(self) -> PluginMultiDict[PluginUploadFile]:
        """Read uploaded files from a multipart request.

        Returns:
            Uploaded file values.
        """
        await self._load_form_parts()
        assert self._files_cache is not None
        return self._files_cache


_request_var: contextvars.ContextVar[PluginRequest] = contextvars.ContextVar(
    "astrbot_plugin_web_request"
)


class PluginRequestProxy:
    """Typed proxy for the request bound to the current plugin Web handler."""

    def _get_current(self) -> PluginRequest:
        try:
            return _request_var.get()
        except LookupError as exc:
            raise RuntimeError(
                "astrbot.api.web.request is only available inside a plugin Web API "
                "handler."
            ) from exc

    @property
    def method(self) -> str:
        return self._get_current().method

    @property
    def path(self) -> str:
        return self._get_current().path

    @property
    def headers(self) -> Headers:
        return self._get_current().headers

    @property
    def cookies(self) -> dict[str, str]:
        return self._get_current().cookies

    @property
    def content_type(self) -> str | None:
        return self._get_current().content_type

    @property
    def client_host(self) -> str | None:
        return self._get_current().client_host

    @property
    def path_params(self) -> dict[str, Any]:
        return self._get_current().path_params

    @property
    def plugin_name(self) -> str | None:
        return self._get_current().plugin_name

    @property
    def username(self) -> str | None:
        return self._get_current().username

    @property
    def query(self) -> PluginMultiDict[str]:
        return self._get_current().query

    async def body(self) -> bytes:
        return await self._get_current().body()

    async def json(self, default: DefaultT | None = None) -> Any | DefaultT | None:
        return await self._get_current().json(default=default)

    async def form(self) -> PluginMultiDict[str]:
        return await self._get_current().form()

    async def files(self) -> PluginMultiDict[PluginUploadFile]:
        return await self._get_current().files()

    def __getattr__(self, key: str) -> Any:
        return getattr(self._get_current(), key)


request: PluginRequestProxy = PluginRequestProxy()


@contextmanager
def bind_request_context(request_: PluginRequest):
    """Bind a plugin Web request for the current async context.

    Args:
        request_: Request object exposed through the module-level request proxy.

    Yields:
        The bound request object.
    """
    token = _request_var.set(request_)
    try:
        yield request_
    finally:
        _request_var.reset(token)


def json_response(
    data: Any = None,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a JSON response for plugin Web API handlers.

    Args:
        data: JSON-serializable response body.
        status_code: HTTP status code.
        headers: Optional response headers.

    Returns:
        A Starlette/FastAPI JSON response.
    """
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
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a standard error response for plugin bridge calls.

    Args:
        message: Public error message.
        status_code: HTTP status code.
        data: Optional error details that are safe to expose.
        headers: Optional response headers.

    Returns:
        A JSON response with the AstrBot error envelope.
    """
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
    headers: dict[str, str] | None = None,
) -> FileResponse:
    """Build a file download response for plugin Web API handlers.

    Args:
        path: File path to send.
        filename: Optional download filename.
        content_type: Optional response media type.
        headers: Optional response headers.

    Returns:
        A Starlette/FastAPI file response.
    """
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
    headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """Build a streaming response for plugin Web API handlers.

    Args:
        content: Sync or async iterable that yields response chunks.
        content_type: Response media type.
        status_code: HTTP status code.
        headers: Optional response headers.

    Returns:
        A Starlette/FastAPI streaming response.
    """
    return StreamingResponse(
        content,
        media_type=content_type,
        status_code=status_code,
        headers=headers,
    )


__all__ = [
    "PluginMultiDict",
    "PluginRequest",
    "PluginRequestProxy",
    "PluginUploadFile",
    "bind_request_context",
    "error_response",
    "file_response",
    "json_response",
    "request",
    "stream_response",
]
