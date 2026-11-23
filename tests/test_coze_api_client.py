"""Coze session ownership and streaming payloads without outbound HTTP."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.runners.coze.coze_api_client import CozeAPIClient


@pytest.mark.asyncio
async def test_session_is_lazy_reused_and_closed_idempotently():
    client = CozeAPIClient("test-key")
    assert client.session is None
    session = await client._ensure_session()
    try:
        assert await client._ensure_session() is session
        assert session.headers["Authorization"] == "Bearer test-key"
        assert session.headers["Accept"] == "text/event-stream"
        assert not session.closed
    finally:
        await client.close()
    assert session.closed and client.session is None
    await client.close()


@pytest.mark.asyncio
async def test_chat_stream_parses_events_and_passes_request_identity():
    client = CozeAPIClient("test-key", "https://example.invalid")
    data = {"content": "你好"}
    frames = [
        b"event: conversation.message.delta\n",
        ("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode(),
    ]

    async def chunks():
        for frame in frames:
            yield frame

    response = MagicMock()
    response.status = 200
    response.content = chunks()
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    client.session = SimpleNamespace(
        post=MagicMock(return_value=response), close=AsyncMock()
    )
    messages = [{"role": "user", "content": "question", "content_type": "text"}]
    events = [
        event
        async for event in client.chat_messages(
            "bot",
            "user",
            messages,
            conversation_id="conversation",
            auto_save_history=False,
            timeout=9,
        )
    ]
    assert events == [{"event": "conversation.message.delta", "data": data}]
    args, kwargs = client.session.post.call_args
    assert args == ("https://example.invalid/v3/chat",)
    assert kwargs["params"] == {"conversation_id": "conversation"}
    assert kwargs["json"] == {
        "bot_id": "bot",
        "user_id": "user",
        "stream": True,
        "auto_save_history": False,
        "additional_messages": messages,
    }
    assert kwargs["timeout"].total == 9


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 500])
async def test_chat_http_failure_closes_response_context(status):
    client = CozeAPIClient("test-key", "https://example.invalid")
    response = MagicMock()
    response.status = status
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    client.session = SimpleNamespace(
        post=MagicMock(return_value=response), close=AsyncMock()
    )
    with pytest.raises(Exception, match="认证失败" if status == 401 else "500"):
        _ = [item async for item in client.chat_messages("bot", "user")]
    response.__aexit__.assert_awaited_once()
