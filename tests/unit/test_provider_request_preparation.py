"""Tests for copy-on-write provider request preparation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.llm_types import LLMResponse, ProviderRequest
from astrbot.core.agent.request_preparation import prepare_provider_request
from astrbot.core.execution_context import CoreExecutionContext
from astrbot.core.provider.provider import Provider


class _SDKProvider(Provider):
    def __init__(self) -> None:
        super().__init__({"id": "sdk", "modalities": ["text"]}, {})
        self.request_kwargs: dict = {}

    def get_current_key(self) -> str:
        return ""

    def set_key(self, key: str) -> None:
        del key

    async def get_models(self) -> list[str]:
        return []

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.request_kwargs = kwargs
        return LLMResponse(role="assistant", completion_text="prepared")


@pytest.mark.asyncio
async def test_prepare_provider_request_does_not_mutate_and_rejects_remote_media():
    data_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL9mQAAAABJRU5ErkJggg=="
    request = ProviderRequest(
        prompt="describe",
        image_urls=[data_image, "http://127.0.0.1/private.png"],
        contexts=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_image},
                    }
                ],
            }
        ],
    )

    prepared = await prepare_provider_request(request)

    assert request.image_urls == [data_image, "http://127.0.0.1/private.png"]
    assert len(prepared.image_urls) == 1
    assert prepared.image_urls[0].startswith("data:image/png;base64,")
    assert "data:image" not in str(prepared.contexts)
    assert any(
        "image omitted" in part.text for part in prepared.extra_user_content_parts
    )


@pytest.mark.asyncio
async def test_prepare_provider_request_downgrades_unsupported_media_without_hooks():
    provider = MagicMock()
    provider.provider_config = {"modalities": ["text"]}
    request = ProviderRequest(image_urls=["base64://aGVsbG8="])

    prepared = await prepare_provider_request(request, provider=provider)

    assert prepared.image_urls == []
    assert any(
        "image omitted" in part.text for part in prepared.extra_user_content_parts
    )
    assert request.extra_user_content_parts == []


@pytest.mark.asyncio
async def test_sdk_llm_generate_uses_shared_preparation_without_global_hook():
    provider = _SDKProvider()
    context = CoreExecutionContext.__new__(CoreExecutionContext)
    context.provider_manager = SimpleNamespace(
        get_provider_by_id=AsyncMock(return_value=provider),
    )
    data_image = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/"
        "ScL9mQAAAABJRU5ErkJggg=="
    )

    response = await context.llm_generate(
        chat_provider_id="sdk",
        prompt="describe",
        image_urls=[data_image],
    )

    assert response.completion_text == "prepared"
    assert provider.request_kwargs["image_urls"] == []
    assert any(
        "image omitted" in part.text
        for part in provider.request_kwargs["extra_user_content_parts"]
    )
    assert not hasattr(context, "handlers")
