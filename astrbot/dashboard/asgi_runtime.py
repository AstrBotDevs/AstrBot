from __future__ import annotations

import contextvars
import inspect
import re
from collections.abc import Callable, Iterable
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.responses import StreamingResponse

_request_var: contextvars.ContextVar[DashboardRequest] = contextvars.ContextVar(
    "dashboard_request"
)
_websocket_var: contextvars.ContextVar[DashboardWebSocket] = contextvars.ContextVar(
    "dashboard_websocket"
)
_g_var: contextvars.ContextVar[DashboardRequestState] = contextvars.ContextVar(
    "dashboard_g"
)
_app_var: contextvars.ContextVar[FastAPIAppAdapter] = contextvars.ContextVar(
    "dashboard_app"
)


class RequestArgs:
    def __init__(self, values) -> None:
        self._values = values

    def get(self, key: str, default: Any = None, type: Callable | None = None):
        value = self._values.get(key, default)
        if value is default or type is None:
            return value
        try:
            return type(value)
        except (TypeError, ValueError):
            return default


class RequestMultiDict:
    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        self._pairs = pairs

    def get(self, key: str, default: Any = None, type: Callable | None = None):
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

    def getlist(self, key: str) -> list[Any]:
        return [item_value for item_key, item_value in self._pairs if item_key == key]

    def keys(self):
        return dict.fromkeys(item_key for item_key, _ in self._pairs).keys()

    def values(self):
        return [self[key] for key in self.keys()]

    def items(self):
        return [(key, self[key]) for key in self.keys()]

    def __contains__(self, key: str) -> bool:
        return any(item_key == key for item_key, _ in self._pairs)

    def __getitem__(self, key: str):
        value = self.get(key)
        if value is None and key not in self:
            raise KeyError(key)
        return value

    def __bool__(self) -> bool:
        return bool(self._pairs)


class RequestUploadFile:
    def __init__(self, upload_file: StarletteUploadFile) -> None:
        self._upload_file = upload_file
        self.filename = upload_file.filename
        self.content_type = upload_file.content_type
        self.headers = upload_file.headers
        self.content_length = self._resolve_content_length()

    def _resolve_content_length(self) -> int | None:
        try:
            raw = self.headers.get("content-length")
            return int(raw) if raw else None
        except (TypeError, ValueError):
            return None

    async def save(self, destination: str | Path) -> None:
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

    def __getattr__(self, key: str):
        return getattr(self._upload_file, key)


class DashboardRequestState:
    def __init__(self) -> None:
        self._values: dict[str, Any] = {}

    def get(self, key: str, default: Any = None):
        return self._values.get(key, default)

    def __getattr__(self, key: str):
        try:
            return self._values[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        if key == "_values":
            super().__setattr__(key, value)
            return
        self._values[key] = value


class DashboardRequest:
    def __init__(self, request: Request) -> None:
        self._request = request
        self.args = RequestArgs(request.query_params)
        self.headers = request.headers
        self.cookies = request.cookies
        self.method = request.method
        self.path = request.url.path
        self.content_type = request.headers.get("content-type")
        self.remote_addr = request.client.host if request.client else None
        self._form_cache: RequestMultiDict | None = None
        self._files_cache: RequestMultiDict | None = None

    @property
    def json(self):
        return self.get_json()

    @property
    def files(self):
        return self._load_files()

    @property
    def form(self):
        return self._load_form()

    async def get_json(self, silent: bool = False):
        try:
            return await self._request.json()
        except Exception:
            if silent:
                return None
            raise

    async def _load_form_parts(self) -> None:
        if self._form_cache is not None and self._files_cache is not None:
            return
        form = await self._request.form()
        form_pairs: list[tuple[str, Any]] = []
        file_pairs: list[tuple[str, Any]] = []
        for key, value in form.multi_items():
            if isinstance(value, StarletteUploadFile):
                file_pairs.append((key, RequestUploadFile(value)))
            else:
                form_pairs.append((key, value))
        self._form_cache = RequestMultiDict(form_pairs)
        self._files_cache = RequestMultiDict(file_pairs)

    async def _load_form(self) -> RequestMultiDict:
        await self._load_form_parts()
        assert self._form_cache is not None
        return self._form_cache

    async def _load_files(self) -> RequestMultiDict:
        await self._load_form_parts()
        assert self._files_cache is not None
        return self._files_cache

    async def get_data(self) -> bytes:
        """Return the raw request body as bytes.

        Returns:
            The raw body bytes of the request.
        """
        return await self._request.body()


class DashboardWebSocket:
    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self.args = RequestArgs(websocket.query_params)
        self.headers = websocket.headers

    async def accept(self) -> None:
        await self._websocket.accept()

    async def receive_json(self):
        return await self._websocket.receive_json()

    async def send_json(self, payload: Any) -> None:
        await self._websocket.send_json(payload)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        await self._websocket.close(code=code, reason=reason or "")


class AdapterTestHeaders:
    def __init__(self, headers: httpx.Headers) -> None:
        self._headers = headers

    def getlist(self, key: str) -> list[str]:
        values = self._headers.get_list(key)
        if key.lower() == "set-cookie":
            return [value.replace('=""', "=") for value in values]
        return values

    def get(self, key: str, default: Any = None):
        value = self._headers.get(key, default)
        if isinstance(value, str) and key.lower() == "set-cookie":
            return value.replace('=""', "=")
        return value

    def __getitem__(self, key: str):
        return self._headers[key]

    def __contains__(self, key: str) -> bool:
        return key in self._headers


class AdapterTestResponse:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.status_code = response.status_code
        self.headers = AdapterTestHeaders(response.headers)
        self.data = response.content
        self.content = response.content
        self.text = response.text

    async def get_json(self):
        return self._response.json()

    async def get_data(self):
        return self._response.content


class AdapterTestClient:
    def __init__(self, app: FastAPI) -> None:
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    @staticmethod
    def _is_file_storage(value: Any) -> bool:
        return hasattr(value, "stream") and hasattr(value, "filename")

    @classmethod
    def _file_tuple(cls, value: Any):
        stream = value.stream
        if hasattr(stream, "seek"):
            stream.seek(0)
        content = stream.read()
        filename = getattr(value, "filename", "upload.bin")
        content_type = getattr(value, "content_type", None)
        return filename, content, content_type

    @classmethod
    def _normalize_data(cls, data: Any):
        if not isinstance(data, dict):
            return data, None

        form: dict[str, Any] = {}
        files: list[tuple[str, tuple]] = []
        for key, value in data.items():
            if cls._is_file_storage(value):
                files.append((key, cls._file_tuple(value)))
                continue
            if isinstance(value, Iterable) and not isinstance(
                value, str | bytes | dict
            ):
                values = list(value)
                if values and all(cls._is_file_storage(item) for item in values):
                    files.extend((key, cls._file_tuple(item)) for item in values)
                    continue
            form[key] = value
        return form, files or None

    @classmethod
    def _normalize_files(cls, files: Any):
        if isinstance(files, dict):
            items = files.items()
        elif isinstance(files, Iterable) and not isinstance(files, str | bytes):
            items = files
        else:
            return files

        normalized_files: list[tuple[str, Any]] = []
        for key, value in items:
            if cls._is_file_storage(value):
                normalized_files.append((key, cls._file_tuple(value)))
                continue
            if isinstance(value, Iterable) and not isinstance(
                value, str | bytes | dict
            ):
                values = list(value)
                if values and all(cls._is_file_storage(item) for item in values):
                    normalized_files.extend(
                        (key, cls._file_tuple(item)) for item in values
                    )
                    continue
            normalized_files.append((key, value))
        return normalized_files

    async def request(self, method: str, url: str, **kwargs):
        data = kwargs.pop("data", None)
        if data is not None and "files" not in kwargs:
            normalized_data, files = self._normalize_data(data)
            kwargs["data"] = normalized_data
            if files:
                kwargs["files"] = files
        elif data is not None:
            kwargs["data"] = data
        if "files" in kwargs:
            kwargs["files"] = self._normalize_files(kwargs["files"])
        response = await self._client.request(method, url, **kwargs)
        return AdapterTestResponse(response)

    async def get(self, url: str, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs):
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs):
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs):
        return await self.request("DELETE", url, **kwargs)


class _ContextProxy:
    def __init__(self, var) -> None:
        self._var = var

    def __getattr__(self, key: str):
        return getattr(self._var.get(), key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key == "_var":
            super().__setattr__(key, value)
            return
        setattr(self._var.get(), key, value)


request = _ContextProxy(_request_var)
websocket = _ContextProxy(_websocket_var)
g = _ContextProxy(_g_var)
current_app = _ContextProxy(_app_var)


@contextmanager
def bind_request_context(
    request_: Request,
    app: FastAPIAppAdapter,
    g_obj: DashboardRequestState | None = None,
):
    token_request = _request_var.set(DashboardRequest(request_))
    token_g = _g_var.set(
        g_obj or getattr(request_.state, "dashboard_g", DashboardRequestState())
    )
    token_app = _app_var.set(app)
    try:
        yield _g_var.get()
    finally:
        _app_var.reset(token_app)
        _g_var.reset(token_g)
        _request_var.reset(token_request)


@contextmanager
def bind_websocket_context(
    websocket_: WebSocket,
    app: FastAPIAppAdapter,
    g_obj: DashboardRequestState | None = None,
):
    token_websocket = _websocket_var.set(DashboardWebSocket(websocket_))
    token_g = _g_var.set(
        g_obj or getattr(websocket_.state, "dashboard_g", DashboardRequestState())
    )
    token_app = _app_var.set(app)
    try:
        yield
    finally:
        _app_var.reset(token_app)
        _g_var.reset(token_g)
        _websocket_var.reset(token_websocket)


def jsonify(payload: Any = None):
    return JSONResponse(payload if payload is not None else {})


async def make_response(*args):
    if not args:
        return Response()
    content = args[0]
    status_code = args[1] if len(args) > 1 and isinstance(args[1], int) else None
    headers = args[1] if len(args) > 1 and isinstance(args[1], dict) else None
    if len(args) > 2 and isinstance(args[2], dict):
        headers = args[2]
    if isinstance(content, Response):
        if status_code is not None:
            content.status_code = status_code
        if headers:
            content.headers.update(headers)
        return content
    if hasattr(content, "__aiter__"):
        return StreamingResponse(
            content,
            status_code=status_code or 200,
            headers=headers,
        )
    return Response(
        content=content,
        status_code=status_code or 200,
        headers=headers,
    )


async def send_file(path: str | Path, mimetype: str | None = None, **kwargs):
    filename = kwargs.get("attachment_filename") or kwargs.get("download_name")
    as_attachment = bool(kwargs.get("as_attachment"))
    return FileResponse(
        path,
        media_type=mimetype,
        filename=filename if as_attachment else None,
    )


def abort(status_code: int):
    raise HTTPException(status_code=status_code)


def _convert_rule(path: str) -> str:
    converted = re.sub(r"<path:([A-Za-z_][A-Za-z0-9_]*)>", r"{\1:path}", path)
    converted = re.sub(r"<([A-Za-z_][A-Za-z0-9_]*)>", r"{\1}", converted)
    return converted


async def _call_view(view_func: Callable, path_params: dict[str, Any]):
    result = view_func(**path_params)
    if inspect.isawaitable(result):
        result = await result
    return await _coerce_view_result(result)


async def _coerce_view_result(result: Any):
    if isinstance(result, Response):
        return result
    if _is_quart_response(result):
        return await _quart_response_to_starlette(result)

    if isinstance(result, tuple):
        content = result[0] if result else None
        status_code = next((item for item in result[1:] if isinstance(item, int)), 200)
        headers = next(
            (item for item in result[1:] if isinstance(item, dict)),
            None,
        )
        if content is not None and isinstance(content, Response):
            content.status_code = status_code
            if headers:
                content.headers.update(headers)
            return content
        if _is_quart_response(content):
            return await _quart_response_to_starlette(
                content,
                status_code=status_code,
                extra_headers=headers,
            )
        return _response_from_content(content, status_code=status_code, headers=headers)

    if isinstance(result, dict | list):
        return JSONResponse(jsonable_encoder(result))
    return result


def _response_from_content(
    content: Any,
    *,
    status_code: int,
    headers: dict[str, str] | None = None,
):
    if isinstance(content, dict | list):
        return JSONResponse(
            jsonable_encoder(content),
            status_code=status_code,
            headers=headers,
        )
    return Response(
        content=content,
        status_code=status_code,
        headers=headers,
    )


def _is_quart_response(value: Any) -> bool:
    return (
        hasattr(value, "get_data")
        and inspect.iscoroutinefunction(value.get_data)
        and hasattr(value, "headers")
        and hasattr(value, "status_code")
    )


def _response_header_pairs(headers: Any) -> list[tuple[str, str]]:
    if headers is None:
        return []
    if hasattr(headers, "to_wsgi_list"):
        return [(str(key), str(value)) for key, value in headers.to_wsgi_list()]
    if hasattr(headers, "items"):
        return [(str(key), str(value)) for key, value in headers.items()]
    return [(str(key), str(value)) for key, value in headers]


async def _quart_response_to_starlette(
    quart_response: Any,
    *,
    status_code: int | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Response:
    content = await quart_response.get_data()
    response = Response(
        content=content,
        status_code=status_code or int(quart_response.status_code),
    )
    pairs = _response_header_pairs(quart_response.headers)
    if extra_headers:
        pairs.extend((str(key), str(value)) for key, value in extra_headers.items())
    response.raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in pairs
    ]
    return response


@asynccontextmanager
async def bind_quart_request_context(
    request_: Request,
    app: FastAPIAppAdapter,
    *,
    path: str | None = None,
    g_obj: DashboardRequestState | None = None,
):
    try:
        from quart import g as quart_g
    except ImportError:
        yield
        return

    quart_app = app.get_quart_compat_app()
    headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in request_.scope.get("headers", [])
    }
    body = await request_.body()
    request_path = path or str(request_.url.path)
    if "?" not in request_path and request_.url.query:
        request_path = f"{request_path}?{request_.url.query}"

    async with quart_app.test_request_context(
        request_path,
        method=request_.method,
        headers=headers,
        data=body,
        scheme=request_.url.scheme,
        root_path=request_.scope.get("root_path", ""),
        scope_base={
            "client": request_.scope.get("client"),
            "server": request_.scope.get("server"),
        },
    ):
        if g_obj is not None:
            for key, value in getattr(g_obj, "_values", {}).items():
                setattr(quart_g, key, value)
        yield


async def call_request_view(
    request_: Request,
    app: FastAPIAppAdapter,
    view_func: Callable,
    path_params: dict[str, Any] | None = None,
    g_obj: DashboardRequestState | None = None,
    quart_compat_path: str | None = None,
):
    with bind_request_context(request_, app, g_obj):
        async with bind_quart_request_context(
            request_,
            app,
            path=quart_compat_path,
            g_obj=g_obj,
        ):
            return await _call_view(view_func, path_params or {})


async def call_websocket_view(
    websocket_: WebSocket,
    app: FastAPIAppAdapter,
    view_func: Callable,
    path_params: dict[str, Any] | None = None,
    *,
    accept: bool = True,
):
    if accept:
        await websocket_.accept()
    with bind_websocket_context(websocket_, app):
        return await _call_view(view_func, path_params or {})


class FastAPIAppAdapter:
    def __init__(self, app: FastAPI, static_folder: str | None = None) -> None:
        self._app = app
        app.state.dashboard_app_adapter = self
        self.static_folder = static_folder
        self._dashboard_server: Any | None = None
        self.config: dict[str, Any] = {}
        self.debug = False
        self.testing = False
        self.name = "dashboard"
        self._quart_compat_app: Any | None = None

    def get_quart_compat_app(self):
        if self._quart_compat_app is None:
            from quart import Quart

            self._quart_compat_app = Quart("astrbot_dashboard_plugin_compat")
            self._quart_compat_app.json.sort_keys = False
        return self._quart_compat_app

    def add_url_rule(
        self,
        path: str,
        view_func: Callable,
        methods: list[str] | None = None,
        endpoint: str | None = None,
    ) -> None:
        route_path = _convert_rule(path)
        methods = methods or ["GET"]

        async def endpoint_func(request_: Request):
            with bind_request_context(request_, self):
                return await _call_view(view_func, dict(request_.path_params))

        self._app.add_api_route(
            route_path,
            endpoint_func,
            methods=methods,
            name=endpoint,
            include_in_schema=False,
        )

    def websocket(self, path: str):
        route_path = _convert_rule(path)

        def decorator(view_func: Callable):
            async def endpoint_func(websocket_: WebSocket):
                return await call_websocket_view(
                    websocket_,
                    self,
                    view_func,
                    dict(websocket_.path_params),
                )

            self._app.add_api_websocket_route(
                route_path,
                endpoint_func,
                name=getattr(view_func, "__name__", None),
            )
            return view_func

        return decorator

    def errorhandler(self, _status_code: int):
        def decorator(func: Callable):
            return func

        return decorator

    async def send_static_file(self, filename: str):
        if not self.static_folder:
            raise HTTPException(status_code=404)
        return FileResponse(Path(self.static_folder) / filename)

    def test_client(self):
        self.testing = True
        return AdapterTestClient(self._app)


AdapterResponse = Response
