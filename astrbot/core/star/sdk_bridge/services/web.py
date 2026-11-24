"""Web route service: replay dashboard HTTP requests to bridged plugins.

Routes declared in the Runner handshake are attached to the dashboard web
route registry. Each incoming request is sanitized (dashboard
credentials never cross the boundary), replayed to the Runner, and the
response chunks are pumped back as a starlette StreamingResponse.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest, NotFound
from astrbot_sdk.web import INLINE_BODY_LIMIT, WebRequestInfo

from .base import HostService

if TYPE_CHECKING:
    from ..bridge import SDKPluginBridge

# Dashboard credentials stay on the Host.
_STRIPPED_HEADERS = frozenset({"cookie", "authorization", "proxy-authorization"})

_BODY_TOKEN_TTL_SECONDS = 300.0
_BODY_CHUNK_SIZE = 1024 * 1024


class WebRouteService(HostService):
    """Serve the web.route capability for one bridged plugin."""

    capability_id = "web.route"

    def __init__(self, bridge: SDKPluginBridge) -> None:
        self._bridge = bridge
        self._body_tokens: dict[str, tuple[bytes, float]] = {}

    def register_route(self, route: str, methods: list[str], description: str) -> None:
        """Attach one plugin route to the dashboard registry."""
        view_handler = self._make_view_handler(route)
        registered = self._bridge.context.registered_web_apis
        method_tuple = tuple(method.upper() for method in methods)
        for idx, api in enumerate(registered):
            if api[0] == route and list(method_tuple) == api[2]:
                registered[idx] = (route, view_handler, list(method_tuple), description)
                return
        registered.append((route, view_handler, list(method_tuple), description))
        self._bridge._web_routes.append((route, method_tuple))

    def unregister_all(self) -> None:
        """Detach every route this plugin registered (bridge shutdown)."""
        registered = self._bridge.context.registered_web_apis
        owned = set(self._bridge._web_routes)
        registered[:] = [
            api for api in registered if (api[0], tuple(api[2])) not in owned
        ]
        self._bridge._web_routes.clear()

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve runner-initiated operations."""
        if operation == "read_body":
            token = payload.get("token")
            offset = payload.get("offset", 0)
            if not isinstance(token, str) or not isinstance(offset, int):
                raise InvalidRequest("read_body requires token and offset")
            entry = self._body_tokens.get(token)
            if entry is None or entry[1] < time.monotonic():
                self._body_tokens.pop(token, None)
                raise NotFound("body token expired or unknown")
            body = entry[0]
            chunk = body[offset : offset + _BODY_CHUNK_SIZE]
            done = offset + len(chunk) >= len(body)
            if done:
                self._body_tokens.pop(token, None)
            return {"chunk": chunk, "done": done}
        raise NotFound(f"unknown web.route operation: {operation}")

    def _make_view_handler(self, route: str) -> Any:
        """Build the dashboard view handler replaying requests to the Runner."""
        service = self

        async def view_handler(**path_values: str) -> Any:
            from astrbot.api.web import request as plugin_request

            method = plugin_request.method
            headers = {
                key.lower(): value
                for key, value in plugin_request.headers.items()
                if key.lower() not in _STRIPPED_HEADERS
            }
            body = await plugin_request.body()
            inline_body = None
            body_token = None
            if len(body) <= INLINE_BODY_LIMIT:
                inline_body = body
            else:
                body_token = uuid.uuid4().hex
                service._body_tokens[body_token] = (
                    body,
                    time.monotonic() + _BODY_TOKEN_TTL_SECONDS,
                )
            query_pairs = tuple(
                (str(key), str(value)) for key, value in plugin_request.query.items()
            )
            request = WebRequestInfo(
                route=route,
                method=method.upper(),
                path=plugin_request.path,
                path_params={str(k): str(v) for k, v in path_values.items()},
                query=query_pairs,
                headers=headers,
                body=inline_body,
                body_size=len(body),
                body_token=body_token,
                username=plugin_request.username,
                client_host=plugin_request.client_host,
            )
            client = service._bridge._require_client()
            stream = client.invoke_web(request)
            first = await anext(stream)
            info = first.get("info")
            if info is None:
                raise InvalidRequest("web route stream must start with response info")

            async def chunks() -> AsyncIterator[bytes]:
                async for item in stream:
                    chunk = item.get("chunk")
                    if chunk:
                        yield chunk

            from starlette.responses import StreamingResponse

            return StreamingResponse(
                chunks(),
                status_code=info.status,
                headers={str(k): str(v) for k, v in info.headers.items()},
            )

        return view_handler
