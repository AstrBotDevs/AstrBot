"""Dify request payloads and SSE framing through the real client code."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.runners.dify import dify_api_client as api


def make_response(payload, *, status=200, chunks=None):
    """Expose only an HTTP response boundary; parsing remains production code."""
    encoded = ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode()

    async def iterate(size):
        assert size == 8192
        for chunk in chunks if chunks is not None else [encoded]:
            yield chunk

    response = MagicMock()
    response.status = status
    response.content = SimpleNamespace(iter_chunked=iterate)
    response.text = AsyncMock(return_value="controlled HTTP failure")
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    return response


@pytest.mark.asyncio
@pytest.mark.parametrize("width", [1, 2, 7, 1000])
async def test_sse_handles_utf8_and_crlf_split_across_chunks(width):
    first = {"event": "message", "answer": "你好"}
    last = {"event": "message_end", "id": "complete"}
    data = (
        "data: " + json.dumps(first, ensure_ascii=False) + "\r\n\r\n"
        "data: invalid-json\r\n\r\n"
        "data: " + json.dumps(last)
    ).encode()
    chunks = [data[offset : offset + width] for offset in range(0, len(data), width)]
    assert [
        event async for event in api._stream_sse(make_response({}, chunks=chunks))
    ] == [first, last]


@pytest.fixture
def client_transport(monkeypatch):
    session = SimpleNamespace(post=MagicMock(), close=AsyncMock())
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(api, "ClientSession", factory)
    client = api.DifyAPIClient("test-key", "https://example.invalid/v1")
    factory.assert_called_once_with(trust_env=True)
    return client, session


@pytest.mark.asyncio
async def test_chat_payload_keeps_session_files_authentication_and_timeout(
    client_transport,
):
    client, session = client_transport
    payload = {"event": "message", "answer": "answer"}
    session.post.return_value = make_response(payload)
    files = [{"type": "image", "upload_file_id": "image-1"}]
    result = [
        event
        async for event in client.chat_messages(
            {"mode": "test"},
            "question",
            "caller",
            conversation_id="conversation",
            files=files,
            request_timeout=9,
        )
    ]
    assert result == [payload]
    args, kwargs = session.post.call_args
    assert args == ("https://example.invalid/v1/chat-messages",)
    assert kwargs["headers"] == {"Authorization": "Bearer test-key"}
    assert kwargs["timeout"].total == 9
    assert kwargs["json"] == {
        "inputs": {"mode": "test"},
        "query": "question",
        "user": "caller",
        "response_mode": "streaming",
        "conversation_id": "conversation",
        "files": files,
    }
    await client.close()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflow_uses_empty_file_list_without_mutating_inputs(client_transport):
    client, session = client_transport
    session.post.return_value = make_response({"event": "workflow_finished"})
    inputs = {"question": "hello"}
    assert [item async for item in client.workflow_run(inputs, "caller")] == [
        {"event": "workflow_finished"}
    ]
    args, kwargs = session.post.call_args
    assert args == ("https://example.invalid/v1/workflows/run",)
    assert kwargs["json"] == {
        "inputs": inputs,
        "user": "caller",
        "response_mode": "streaming",
        "files": [],
    }
    assert inputs == {"question": "hello"}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 429, 500])
async def test_http_errors_surface_status_and_body(client_transport, status):
    client, session = client_transport
    session.post.return_value = make_response({}, status=status)
    with pytest.raises(Exception, match=f"{status}.*controlled HTTP failure"):
        _ = [item async for item in client.chat_messages({}, "question", "caller")]
