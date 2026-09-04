"""Tests for bounded HTTP requests to untrusted URLs."""

from __future__ import annotations

import ipaddress

import pytest
from aiohttp import web

from astrbot.core.utils.safe_http import (
    PrivateTargetRule,
    RemoteFetchPolicy,
    RemoteRedirectError,
    RemoteResponseTooLarge,
    UnsafeRemoteTarget,
    _read_response_body,
    fetch_public_json,
    read_public_bytes,
    safe_url_for_log,
)


def _policy(*, max_bytes: int = 1024, allow_loopback: bool = False):
    rules = ()
    if allow_loopback:
        rules = (
            PrivateTargetRule(
                host="127.0.0.1",
                networks=(ipaddress.ip_network("127.0.0.0/8"),),
            ),
        )
    return RemoteFetchPolicy(
        max_bytes=max_bytes,
        total_timeout_seconds=5,
        max_redirects=1,
        allow_private_targets=rules,
    )


async def _serve(handler):
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets  # noqa: SLF001
    port = sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


@pytest.mark.asyncio
async def test_loopback_is_blocked_before_request() -> None:
    with pytest.raises(UnsafeRemoteTarget):
        await read_public_bytes(
            "http://127.0.0.1:1/private",
            policy=_policy(),
        )


@pytest.mark.asyncio
async def test_exact_host_and_cidr_allow_private_target() -> None:
    async def handler(_request):
        return web.json_response({"ok": True})

    runner, base_url = await _serve(handler)
    try:
        result = await fetch_public_json(
            f"{base_url}/data",
            policy=_policy(allow_loopback=True),
        )
        assert result == {"ok": True}
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_streamed_response_over_limit_is_rejected() -> None:
    async def handler(_request):
        response = web.StreamResponse(status=200)
        await response.prepare(_request)
        await response.write(b"a" * 2048)
        await response.write_eof()
        return response

    runner, base_url = await _serve(handler)
    try:
        with pytest.raises(RemoteResponseTooLarge):
            await read_public_bytes(
                f"{base_url}/large",
                policy=_policy(max_bytes=32, allow_loopback=True),
            )
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_declared_response_over_limit_is_rejected_before_streaming() -> None:
    """A declared oversized body should be rejected without consuming content."""

    class UnexpectedContent:
        def iter_chunked(self, _size):
            raise AssertionError("oversized declared content must not be read")

    response = type(
        "DeclaredLargeResponse",
        (),
        {"headers": {"content-length": "2048"}, "content": UnexpectedContent()},
    )()

    with pytest.raises(RemoteResponseTooLarge):
        await _read_response_body(response, max_bytes=32)


@pytest.mark.asyncio
async def test_redirect_limit_is_enforced() -> None:
    async def handler(request):
        raise web.HTTPFound(location=str(request.url))

    runner, base_url = await _serve(handler)
    try:
        with pytest.raises(RemoteRedirectError):
            await read_public_bytes(
                f"{base_url}/loop",
                policy=_policy(allow_loopback=True),
            )
    finally:
        await runner.cleanup()


def test_safe_url_for_log_removes_sensitive_components() -> None:
    sanitized = safe_url_for_log(
        "https://user:password@example.com/file?token=secret#fragment"
    )
    assert sanitized == "https://example.com/file"
    assert "password" not in sanitized
    assert "secret" not in sanitized
