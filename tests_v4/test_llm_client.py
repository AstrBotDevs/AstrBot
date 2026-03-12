"""
Tests for clients/llm.py - LLMClient and related models.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_sdk.clients.llm import ChatMessage, LLMClient, LLMResponse
from astrbot_sdk.clients._proxy import CapabilityProxy


class TestChatMessage:
    """Tests for ChatMessage model."""

    def test_create_with_role_and_content(self):
        """ChatMessage should have role and content."""
        msg = ChatMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_model_dump(self):
        """ChatMessage should serialize correctly."""
        msg = ChatMessage(role="assistant", content="Hi there")
        data = msg.model_dump()
        assert data == {"role": "assistant", "content": "Hi there"}


class TestLLMResponse:
    """Tests for LLMResponse model."""

    def test_create_with_text_only(self):
        """LLMResponse should work with just text."""
        response = LLMResponse(text="Hello")
        assert response.text == "Hello"
        assert response.usage is None
        assert response.finish_reason is None
        assert response.tool_calls == []

    def test_create_with_all_fields(self):
        """LLMResponse should accept all fields."""
        response = LLMResponse(
            text="Response",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            finish_reason="stop",
            tool_calls=[{"name": "search", "args": {"query": "test"}}],
        )
        assert response.text == "Response"
        assert response.usage["prompt_tokens"] == 10
        assert response.finish_reason == "stop"
        assert len(response.tool_calls) == 1

    def test_model_validate(self):
        """LLMResponse should validate from dict."""
        data = {
            "text": "Validated",
            "usage": {"total_tokens": 100},
            "finish_reason": "length",
            "tool_calls": [],
        }
        response = LLMResponse.model_validate(data)
        assert response.text == "Validated"
        assert response.usage["total_tokens"] == 100


class TestLLMClientInit:
    """Tests for LLMClient initialization."""

    def test_init_with_proxy(self):
        """LLMClient should store proxy reference."""
        proxy = MagicMock(spec=CapabilityProxy)
        client = LLMClient(proxy)
        assert client._proxy is proxy


class TestLLMClientChat:
    """Tests for LLMClient.chat() method."""

    @pytest.mark.asyncio
    async def test_chat_with_prompt_only(self):
        """chat() should work with just prompt."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"text": "Hello back"})

        client = LLMClient(proxy)
        result = await client.chat("Hello")

        proxy.call.assert_called_once()
        call_args = proxy.call.call_args
        assert call_args[0][0] == "llm.chat"
        assert call_args[0][1]["prompt"] == "Hello"
        assert result == "Hello back"

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self):
        """chat() should pass system prompt."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"text": "Response"})

        client = LLMClient(proxy)
        result = await client.chat("Hi", system="Be helpful")

        call_args = proxy.call.call_args[0][1]
        assert call_args["system"] == "Be helpful"
        assert result == "Response"

    @pytest.mark.asyncio
    async def test_chat_with_history(self):
        """chat() should pass conversation history."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"text": "OK"})

        client = LLMClient(proxy)
        history = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi"),
        ]
        await client.chat("How are you?", history=history)

        call_args = proxy.call.call_args[0][1]
        assert len(call_args["history"]) == 2
        assert call_args["history"][0] == {"role": "user", "content": "Hello"}

    @pytest.mark.asyncio
    async def test_chat_with_model_and_temperature(self):
        """chat() should pass model and temperature."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"text": "Done"})

        client = LLMClient(proxy)
        await client.chat("Test", model="gpt-4", temperature=0.5)

        call_args = proxy.call.call_args[0][1]
        assert call_args["model"] == "gpt-4"
        assert call_args["temperature"] == 0.5

    @pytest.mark.asyncio
    async def test_chat_returns_empty_string_for_missing_text(self):
        """chat() should return empty string if text is missing."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = LLMClient(proxy)
        result = await client.chat("Hello")

        assert result == ""


class TestLLMClientChatRaw:
    """Tests for LLMClient.chat_raw() method."""

    @pytest.mark.asyncio
    async def test_chat_raw_returns_llm_response(self):
        """chat_raw() should return LLMResponse object."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(
            return_value={
                "text": "Raw response",
                "usage": {"tokens": 50},
                "finish_reason": "stop",
                "tool_calls": [],
            }
        )

        client = LLMClient(proxy)
        result = await client.chat_raw("Test")

        assert isinstance(result, LLMResponse)
        assert result.text == "Raw response"
        assert result.usage["tokens"] == 50

    @pytest.mark.asyncio
    async def test_chat_raw_passes_kwargs(self):
        """chat_raw() should pass additional kwargs to proxy."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"text": "OK"})

        client = LLMClient(proxy)
        await client.chat_raw("Test", custom_param="value", another=123)

        call_args = proxy.call.call_args[0][1]
        assert call_args["custom_param"] == "value"
        assert call_args["another"] == 123


class TestLLMClientStreamChat:
    """Tests for LLMClient.stream_chat() method."""

    @pytest.mark.asyncio
    async def test_stream_chat_yields_text_chunks(self):
        """stream_chat() should yield text chunks."""
        proxy = MagicMock(spec=CapabilityProxy)

        async def mock_stream(name, payload):
            yield {"text": "Hello"}
            yield {"text": " "}
            yield {"text": "World"}

        proxy.stream = mock_stream

        client = LLMClient(proxy)
        chunks = []
        async for chunk in client.stream_chat("Test"):
            chunks.append(chunk)

        assert chunks == ["Hello", " ", "World"]

    @pytest.mark.asyncio
    async def test_stream_chat_with_system_and_history(self):
        """stream_chat() should pass system and history."""
        proxy = MagicMock(spec=CapabilityProxy)

        captured_payload = None

        async def mock_stream(name, payload):
            nonlocal captured_payload
            captured_payload = payload
            yield {"text": "Done"}

        proxy.stream = mock_stream

        client = LLMClient(proxy)
        history = [ChatMessage(role="user", content="Hi")]
        chunks = []
        async for chunk in client.stream_chat("Test", system="Be nice", history=history):
            chunks.append(chunk)

        assert captured_payload["system"] == "Be nice"
        assert len(captured_payload["history"]) == 1

    @pytest.mark.asyncio
    async def test_stream_chat_yields_empty_string_for_missing_text(self):
        """stream_chat() should yield empty string if text is missing."""
        proxy = MagicMock(spec=CapabilityProxy)

        async def mock_stream(name, payload):
            yield {}
            yield {"other": "data"}

        proxy.stream = mock_stream

        client = LLMClient(proxy)
        chunks = []
        async for chunk in client.stream_chat("Test"):
            chunks.append(chunk)

        assert chunks == ["", ""]
