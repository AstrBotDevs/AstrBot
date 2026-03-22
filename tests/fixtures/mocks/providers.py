"""Mock providers for testing LLM interactions."""

from typing import Any, AsyncGenerator
from dataclasses import dataclass, field

from astrbot.core.provider.entities import (
    ProviderRequest,
    ProviderResponse,
    ProviderMeta,
    ProviderType,
    LLMResponse,
)


class MockChatCompletionProvider:
    """Mock provider that returns predefined responses for testing."""

    def __init__(
        self,
        responses: list[LLMResponse] | None = None,
        streaming_responses: list[list[str]] | None = None,
    ):
        self.responses = responses or []
        self.streaming_responses = streaming_responses or []
        self.response_index = 0
        self.call_count = 0
        self.last_request: ProviderRequest | None = None

        self.meta = ProviderMeta(
            id="mock_provider",
            model="mock-model",
            type="mock",
            provider_type=ProviderType.CHAT_COMPLETION,
        )

    async def chat(
        self, request: ProviderRequest
    ) -> LLMResponse | AsyncGenerator[LLMResponse, None]:
        """Return mock chat completion."""
        self.call_count += 1
        self.last_request = request

        if self.responses:
            response = self.responses[self.response_index % len(self.responses)]
            self.response_index += 1
            return response

        # Default mock response
        return LLMResponse(
            role="assistant",
            completion_text="This is a mock response from the test provider.",
        )

    async def stream_chat(self, request: ProviderRequest) -> AsyncGenerator[LLMResponse, None]:
        """Return mock streaming chat completion."""
        self.call_count += 1
        self.last_request = request

        text = "This is a mock streaming response."
        if self.streaming_responses:
            text = self.streaming_responses[self.response_index % len(self.streaming_responses)]
            self.response_index += 1

        # Stream word by word
        for word in text.split():
            yield LLMResponse(
                role="assistant",
                completion_text=word + " ",
            )

    def get_model(self) -> str:
        return "mock-model"

    def get_provider_type(self) -> ProviderType:
        return ProviderType.CHAT_COMPLETION


class MockToolCallProvider(MockChatCompletionProvider):
    """Mock provider that returns tool calls."""

    def __init__(
        self,
        tool_calls: list[dict] | None = None,
        tool_response: str = "Tool executed successfully",
    ):
        super().__init__()
        self.tool_calls = tool_calls or []
        self.tool_response = tool_response
        self.tool_call_count = 0

    async def chat(self, request: ProviderRequest) -> LLMResponse:
        """Return mock tool call."""
        self.call_count += 1

        if self.tool_calls:
            tool_call = self.tool_calls[self.tool_call_count % len(self.tool_calls)]
            self.tool_call_count += 1
            return LLMResponse(
                role="assistant",
                completion_text="",
                tool_calls=[tool_call],
            )

        # Default tool call
        return LLMResponse(
            role="assistant",
            completion_text="",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "mock_tool",
                        "arguments": '{"input": "test"}',
                    },
                }
            ],
        )


class MockErrorProvider(MockChatCompletionProvider):
    """Mock provider that raises errors for testing error handling."""

    def __init__(self, error_message: str = "Mock provider error"):
        super().__init__()
        self.error_message = error_message

    async def chat(self, request: ProviderRequest) -> LLMResponse:
        """Raise mock error."""
        raise RuntimeError(self.error_message)

    async def stream_chat(self, request: ProviderRequest) -> AsyncGenerator[LLMResponse, None]:
        """Raise mock error."""
        raise RuntimeError(self.error_message)


class MockMultiModalProvider(MockChatCompletionProvider):
    """Mock provider for multimodal interactions."""

    def __init__(
        self,
        has_image_support: bool = True,
        has_audio_support: bool = False,
    ):
        super().__init__()
        self.has_image_support = has_image_support
        self.has_audio_support = has_audio_support

    async def chat(self, request: ProviderRequest) -> LLMResponse:
        """Return response based on request content."""
        has_images = bool(request.image_urls)

        if has_images and not self.has_image_support:
            return LLMResponse(
                role="assistant",
                completion_text="Image support not enabled.",
            )

        return LLMResponse(
            role="assistant",
            completion_text=f"Received request with {len(request.image_urls)} images.",
        )


def create_mock_provider_request(
    prompt: str = "Hello, test!",
    session_id: str = "test-session-1",
    image_urls: list[str] | None = None,
) -> ProviderRequest:
    """Create a mock provider request for testing."""
    return ProviderRequest(
        prompt=prompt,
        session_id=session_id,
        image_urls=image_urls or [],
    )


def create_mock_llm_response(
    text: str = "Mock response",
    tool_calls: list[dict] | None = None,
) -> LLMResponse:
    """Create a mock LLM response for testing."""
    return LLMResponse(
        role="assistant",
        completion_text=text,
        tool_calls=tool_calls,
    )
