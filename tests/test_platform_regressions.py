"""Platform regressions using the real ASGI request wrapper."""

import pytest
from starlette.requests import Request

from astrbot.dashboard.asgi_runtime import DashboardRequest


def make_webhook_request(
    body: bytes,
    headers: dict[str, str] | None = None,
) -> DashboardRequest:
    """Build a real request with one bounded ASGI body message and no network."""
    values = {key.lower(): value for key, value in (headers or {}).items()}
    values.setdefault("content-type", "application/json")
    events = iter([{"type": "http.request", "body": body, "more_body": False}])

    async def receive():
        return next(events, {"type": "http.disconnect"})

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/platform/webhook/test",
        "raw_path": b"/api/platform/webhook/test",
        "root_path": "",
        "query_string": b"",
        "headers": [
            (key.encode("latin-1"), value.encode("latin-1"))
            for key, value in values.items()
        ],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
    }
    return DashboardRequest(Request(scope, receive=receive))


@pytest.mark.asyncio
@pytest.mark.parametrize("header_name", ["x-signature", "X-Signature"])
async def test_platform_webhook_request_preserves_signed_bytes(header_name):
    body = b' { "message": "hello" }\n'
    request = make_webhook_request(body, {header_name: "signature-1"})

    assert await request.get_data() == body
    assert await request.get_json() == {"message": "hello"}
    assert await request.get_data() == body
    assert request.headers["x-signature"] == "signature-1"
