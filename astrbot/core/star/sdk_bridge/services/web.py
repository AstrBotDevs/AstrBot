"""Web route service: replay dashboard HTTP requests to bridged plugins.

Routes registered by plugins (handshake declarations or dynamic register
calls) are attached to the same registered_web_apis registry the legacy
in-process API uses. Each incoming request is sanitized (dashboard
credentials never cross the boundary), replayed to the Runner, and the
response chunks are pumped back as a starlette StreamingResponse.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import jwt
from astrbot_sdk.errors import InvalidRequest, NotFound
from astrbot_sdk.web import INLINE_BODY_LIMIT, WebRequestInfo

from astrbot.dashboard.plugin_page_auth import (
    PLUGIN_PAGE_TOKEN_TYPE,
    WILDCARD_PAGE_SCOPE,
)

from .base import HostService

if TYPE_CHECKING:
    from ..bridge import SDKPluginBridge

# Headers carrying dashboard credentials or hop-by-hop proxy auth never
# cross to plugins. "authorization" is handled separately: it is swapped for
# a plugin-scoped view token instead of being forwarded raw.
_STRIPPED_HEADERS = frozenset({"cookie", "authorization", "proxy-authorization"})

# Lifetime of the scoped view token replacing the dashboard credential. View
# scripts cache it for the page session, so it must outlive typical sessions.
# Aligned with the dashboard session lifetime (7 days), same as the
# dashboard-minted view asset tokens.
_VIEW_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60

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
        if operation == "register":
            route = payload.get("route")
            methods = payload.get("methods")
            if not isinstance(route, str) or not route.startswith("/"):
                raise InvalidRequest("register requires a route starting with '/'")
            if not isinstance(methods, list) or not all(
                isinstance(method, str) for method in methods
            ):
                raise InvalidRequest("register requires a methods list")
            self.register_route(
                route,
                methods,
                str(payload.get("description") or ""),
            )
            return {}
        if operation == "unregister":
            route = payload.get("route")
            methods = payload.get("methods") or []
            registered = self._bridge.context.registered_web_apis
            method_tuple = tuple(str(method).upper() for method in methods)
            registered[:] = [
                api
                for api in registered
                if not (api[0] == route and api[2] == list(method_tuple))
            ]
            self._bridge._web_routes = [
                item
                for item in self._bridge._web_routes
                if item != (route, method_tuple)
            ]
            return {}
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

    def _scoped_view_token(self, username: str | None) -> str | None:
        """Mint a plugin-scoped view token replacing a dashboard credential.

        Legacy view code echoes the request's Authorization bearer into plugin
        page URLs (asset_token). Forwarding the raw dashboard JWT would hand
        dashboard admin credentials to the isolated plugin process, so it is
        swapped for a read-only token valid only for this plugin's page assets.

        Args:
            username: Authenticated dashboard username from the request.

        Returns:
            The signed token, or None when it cannot be minted.
        """
        plugin_name = self._bridge.plugin_name
        if not username or not plugin_name:
            return None
        config = self._bridge.context.get_config()
        jwt_secret = config.get("dashboard", {}).get("jwt_secret") if config else None
        if not isinstance(jwt_secret, str) or not jwt_secret:
            return None
        now = datetime.now(timezone.utc)
        payload = {
            "username": username,
            "token_type": PLUGIN_PAGE_TOKEN_TYPE,
            "plugin_name": plugin_name,
            "page_name": WILDCARD_PAGE_SCOPE,
            "iat": now,
            "exp": now + timedelta(seconds=_VIEW_TOKEN_TTL_SECONDS),
        }
        return jwt.encode(payload, jwt_secret, algorithm="HS256")

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
            if "authorization" in {key.lower() for key in plugin_request.headers}:
                scoped_token = service._scoped_view_token(plugin_request.username)
                if scoped_token:
                    headers["authorization"] = f"Bearer {scoped_token}"
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
