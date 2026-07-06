from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from hypercorn.asyncio import serve
from hypercorn.config import Config as HyperConfig


class WebhookRequest:
    def __init__(self, request: Request) -> None:
        self._request = request
        self.args = request.query_params
        self.headers = request.headers
        self.method = request.method

    @property
    def json(self):
        return self._request.json()

    async def get_data(self) -> bytes:
        return await self._request.body()

    async def get_json(self, *, force: bool = False, silent: bool = False):
        try:
            return await self._request.json()
        except Exception:
            if silent:
                return None
            raise


def webhook_response_from_result(result: Any):
    """Convert adapter callback results into raw webhook HTTP responses.

    Args:
        result: Adapter callback return value.

    Returns:
        A FastAPI-compatible raw response value.
    """
    if isinstance(result, Response):
        return result

    if isinstance(result, tuple):
        content = result[0] if result else ""
        status_code = (
            result[1] if len(result) > 1 and isinstance(result[1], int) else 200
        )
        headers = result[2] if len(result) > 2 and isinstance(result[2], dict) else None
        if isinstance(content, dict | list):
            return JSONResponse(content, status_code=status_code, headers=headers)
        return Response(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type=headers.get("Content-Type") if headers else None,
        )

    if isinstance(result, dict | list):
        return JSONResponse(result)

    if isinstance(result, str | bytes):
        return Response(content=result)

    return result


class FastAPIWebhookServer:
    def __init__(self, name: str) -> None:
        self.app = FastAPI(title=name, docs_url=None, redoc_url=None, openapi_url=None)

    def add_url_rule(
        self,
        path: str,
        view_func: Callable,
        methods: list[str] | None = None,
    ) -> None:
        has_params = bool(inspect.signature(view_func).parameters)

        async def endpoint(request: Request):
            if has_params:
                result = view_func(WebhookRequest(request))
            else:
                result = view_func()
            if inspect.isawaitable(result):
                result = await result
            return webhook_response_from_result(result)

        self.app.add_api_route(
            path,
            endpoint,
            methods=methods or ["GET"],
            include_in_schema=False,
        )

    def route(self, path: str, methods: list[str] | None = None):
        def decorator(view_func: Callable):
            self.add_url_rule(path, view_func, methods)
            return view_func

        return decorator

    async def run_task(
        self,
        *,
        host: str,
        port: int,
        shutdown_trigger: Callable | None = None,
        **_kwargs,
    ) -> None:
        config = HyperConfig()
        config.bind = [f"{host}:{port}"]
        await serve(self.app, config, shutdown_trigger=shutdown_trigger)

    async def shutdown(self) -> None:
        return None
