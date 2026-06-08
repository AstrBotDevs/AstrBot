from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
import jwt
from fastapi import Request, Response

from astrbot.dashboard.v1.auth import AuthContext

_BODY_NOT_SET = object()
_SKIP_RESPONSE_HEADERS = {
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "server",
}


class DashboardRouteBridgeService:
    """Forward a v1 request to a dashboard compatibility route after v1 auth."""

    def __init__(self, route_app, jwt_secret: str) -> None:
        self.route_app = route_app
        self.jwt_secret = jwt_secret

    def _build_headers(
        self, request: Request, auth: AuthContext | None
    ) -> dict[str, str]:
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in {"authorization", "host"}
        }
        if auth is None:
            return headers
        token = jwt.encode(
            {"username": auth.username},
            self.jwt_secret,
            algorithm="HS256",
        )
        headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _merge_query(
        request: Request,
        query: Mapping[str, Any] | None,
        *,
        drop: set[str] | None = None,
    ) -> list[tuple[str, str]]:
        drop = drop or set()
        pairs = [
            (key, value)
            for key, value in request.query_params.multi_items()
            if key not in drop
        ]
        if query:
            for key, value in query.items():
                if value is None:
                    continue
                if isinstance(value, list | tuple):
                    pairs.extend((key, str(item)) for item in value)
                else:
                    pairs.append((key, str(value)))
        return pairs

    @staticmethod
    def _as_response(response: httpx.Response) -> Response:
        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in _SKIP_RESPONSE_HEADERS
        }
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=headers,
            media_type=headers.get("content-type"),
        )

    async def forward(
        self,
        request: Request,
        auth: AuthContext | None,
        *,
        method: str,
        target_path: str,
        query: Mapping[str, Any] | None = None,
        drop_query: set[str] | None = None,
        json_body: Any = _BODY_NOT_SET,
    ) -> Response:
        headers = self._build_headers(request, auth)
        params = self._merge_query(request, query, drop=drop_query)
        transport = httpx.ASGITransport(app=self.route_app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://dashboard-routes",
        ) as client:
            if json_body is _BODY_NOT_SET:
                response = await client.request(
                    method,
                    target_path,
                    params=params,
                    content=await request.body(),
                    headers=headers,
                )
            else:
                response = await client.request(
                    method,
                    target_path,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
        return self._as_response(response)
