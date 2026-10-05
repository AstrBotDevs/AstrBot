import json
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from astrbot.core.agent.runners.dify.dify_api_client import DifyAPIClient


@pytest_asyncio.fixture
async def dify_client(monkeypatch):
    client = DifyAPIClient(api_key="test-key", api_base="https://dify.example/v1")
    response = MagicMock()
    response.status = 200
    response.__aenter__.return_value = response
    monkeypatch.setattr(client.session, "post", MagicMock(return_value=response))
    try:
        yield client, response
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("line_ending", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize("method", ["chat_messages", "workflow_run"])
async def test_stream_preserves_multiple_sse_events(dify_client, line_ending, method):
    client, response = dify_client

    async def chunks():
        yield (
            f'data: {{"event": "message", "answer": "hello"}}{line_ending}{line_ending}'
            f'data: {{"event": "message_end"}}{line_ending}{line_ending}'
        ).encode()

    response.content.iter_chunked.return_value = chunks()
    kwargs = {"query": "hello"} if method == "chat_messages" else {}
    events = [
        event async for event in getattr(client, method)({}, user="test-user", **kwargs)
    ]

    assert events == [
        {"event": "message", "answer": "hello"},
        {"event": "message_end"},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size", [1, 2, 7, 8192])
@pytest.mark.parametrize(
    "separator", ["\n\n", "\r\n\r\n", "\r\n\n"], ids=["lf", "crlf", "mixed"]
)
async def test_stream_preserves_chunked_utf8_and_unterminated_final_event(
    dify_client, chunk_size, separator
):
    client, response = dify_client
    expected = [
        {"event": "message", "answer": "\u4f60\u597d\U0001f642\r\nnext line"},
        {"event": "message_end"},
    ]
    payload = separator.join(
        f"data: {json.dumps(event, ensure_ascii=False)}" for event in expected
    ).encode("utf-8")

    async def chunks():
        for offset in range(0, len(payload), chunk_size):
            yield payload[offset : offset + chunk_size]

    response.content.iter_chunked.return_value = chunks()
    events = [
        event async for event in client.chat_messages({}, "hello", user="test-user")
    ]

    assert events == expected


@pytest.mark.asyncio
async def test_stream_skips_invalid_events_without_losing_following_events(dify_client):
    client, response = dify_client

    async def chunks():
        yield (
            b": keepalive\r\n\r\n"
            b"data: invalid json\r\n\r\n"
            b'data: {"event": "message_end"}\r\n\r\n'
        )

    response.content.iter_chunked.return_value = chunks()
    events = [
        event async for event in client.chat_messages({}, "hello", user="test-user")
    ]

    assert events == [{"event": "message_end"}]


@pytest.mark.asyncio
async def test_stream_yields_crlf_event_before_reading_more_chunks(dify_client):
    client, response = dify_client

    async def chunks():
        yield b'data: {"event": "message", "answer": "hello"}\r'
        yield b"\n\r"
        yield b"\n"
        pytest.fail("The completed event must be yielded before reading another chunk")

    response.content.iter_chunked.return_value = chunks()
    stream = client.chat_messages({}, "hello", user="test-user")
    try:
        assert await anext(stream) == {"event": "message", "answer": "hello"}
    finally:
        await stream.aclose()
