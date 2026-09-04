"""Tests for Dashboard ASGI request-body limits."""

from __future__ import annotations

import json

import pytest

from astrbot.dashboard.body_limits import (
    BACKUP_CHUNK_REQUEST_LIMIT,
    CONFIG_FILE_LIMIT,
    JSON_LIMIT,
    RequestBodyLimitMiddleware,
    resolve_body_limit,
)


def test_resolve_body_limit_uses_endpoint_policy() -> None:
    assert resolve_body_limit("/api/v1/example", "application/json") == JSON_LIMIT
    assert (
        resolve_body_limit("/api/v1/backups/upload/chunk", "multipart/form-data")
        == BACKUP_CHUNK_REQUEST_LIMIT
    )
    assert (
        resolve_body_limit("/api/config/file/upload", "multipart/form-data")
        == CONFIG_FILE_LIMIT
    )
    assert (
        resolve_body_limit("/api/v1/plugins/config-files", "multipart/form-data")
        == CONFIG_FILE_LIMIT
    )
    assert (
        resolve_body_limit(
            "/api/v1/plugins/demo/config-files/model/path", "multipart/form-data"
        )
        == CONFIG_FILE_LIMIT
    )


@pytest.mark.asyncio
async def test_declared_oversized_body_is_rejected_without_calling_app() -> None:
    called = False

    async def app(_scope, _receive, _send):
        nonlocal called
        called = True

    middleware = RequestBodyLimitMiddleware(app)
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await middleware(
        {
            "type": "http",
            "path": "/api/v1/example",
            "method": "POST",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(JSON_LIMIT + 1).encode()),
            ],
        },
        receive,
        send,
    )

    assert called is False
    assert sent[0]["status"] == 413
    payload = json.loads(sent[1]["body"])
    assert payload["status"] == "error"


@pytest.mark.asyncio
async def test_streamed_body_without_length_is_rejected() -> None:
    chunks = [
        {"type": "http.request", "body": b"a" * JSON_LIMIT, "more_body": True},
        {"type": "http.request", "body": b"b", "more_body": False},
    ]

    async def receive():
        return chunks.pop(0)

    async def app(_scope, limited_receive, _send):
        await limited_receive()
        await limited_receive()

    sent = []

    async def send(message):
        sent.append(message)

    await RequestBodyLimitMiddleware(app)(
        {
            "type": "http",
            "path": "/api/v1/example",
            "method": "POST",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
        send,
    )

    assert sent[0]["status"] == 413
