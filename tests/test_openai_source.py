import pytest

from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


class _ErrorWithBody(Exception):
    def __init__(self, message: str, body: dict):
        super().__init__(message)
        self.body = body


def _make_provider(overrides: dict | None = None) -> ProviderOpenAIOfficial:
    provider_config = {
        "id": "test-openai",
        "type": "openai_chat_completion",
        "model": "gpt-4o-mini",
        "key": ["test-key"],
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderOpenAIOfficial(
        provider_config=provider_config,
        provider_settings={},
    )


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_removes_images():
    provider = _make_provider(
        {"image_moderation_error_patterns": ["file:content-moderated"]}
    )
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]

        success, *_rest = await provider._handle_api_error(
            Exception("Content is moderated [WKE=file:content-moderated]"),
            payloads=payloads,
            context_query=context_query,
            func_tool=None,
            chosen_key="test-key",
            available_api_keys=["test-key"],
            retry_cnt=0,
            max_retries=10,
        )

        assert success is False
        updated_context = payloads["messages"]
        assert isinstance(updated_context, list)
        assert updated_context[0]["content"] == [{"type": "text", "text": "hello"}]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_without_images_raises():
    provider = _make_provider(
        {"image_moderation_error_patterns": ["file:content-moderated"]}
    )
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "hello"}],
                }
            ]
        }
        context_query = payloads["messages"]
        err = Exception("Content is moderated [WKE=file:content-moderated]")

        with pytest.raises(Exception, match="content-moderated"):
            await provider._handle_api_error(
                err,
                payloads=payloads,
                context_query=context_query,
                func_tool=None,
                chosen_key="test-key",
                available_api_keys=["test-key"],
                retry_cnt=0,
                max_retries=10,
            )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_detects_structured_body():
    provider = _make_provider(
        {"image_moderation_error_patterns": ["content_moderated"]}
    )
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]
        err = _ErrorWithBody(
            "upstream error",
            {"error": {"code": "content_moderated", "message": "blocked"}},
        )

        success, *_rest = await provider._handle_api_error(
            err,
            payloads=payloads,
            context_query=context_query,
            func_tool=None,
            chosen_key="test-key",
            available_api_keys=["test-key"],
            retry_cnt=0,
            max_retries=10,
        )
        assert success is False
        assert payloads["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_supports_custom_patterns():
    provider = _make_provider(
        {"image_moderation_error_patterns": ["blocked_by_policy_code_123"]}
    )
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]
        err = Exception("upstream: blocked_by_policy_code_123")

        success, *_rest = await provider._handle_api_error(
            err,
            payloads=payloads,
            context_query=context_query,
            func_tool=None,
            chosen_key="test-key",
            available_api_keys=["test-key"],
            retry_cnt=0,
            max_retries=10,
        )
        assert success is False
        assert payloads["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_without_patterns_raises():
    provider = _make_provider()
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]
        err = Exception("Content is moderated [WKE=file:content-moderated]")

        with pytest.raises(Exception, match="content-moderated"):
            await provider._handle_api_error(
                err,
                payloads=payloads,
                context_query=context_query,
                func_tool=None,
                chosen_key="test-key",
                available_api_keys=["test-key"],
                retry_cnt=0,
                max_retries=10,
            )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_unknown_image_error_raises():
    provider = _make_provider()
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]

        with pytest.raises(Exception, match="unknown provider image upload error"):
            await provider._handle_api_error(
                Exception("some unknown provider image upload error"),
                payloads=payloads,
                context_query=context_query,
                func_tool=None,
                chosen_key="test-key",
                available_api_keys=["test-key"],
                retry_cnt=0,
                max_retries=10,
            )
    finally:
        await provider.terminate()
