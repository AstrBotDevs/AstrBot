from pathlib import Path
from types import SimpleNamespace

import pytest
from openai.types.chat.chat_completion import ChatCompletion

from astrbot.core.agent.message import ImageURLPart
from astrbot.core.provider.sources.groq_source import ProviderGroq
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from tests.fixtures.image_samples import (
    GIF_BASE64,
    GIF_BYTES,
    JPEG_BASE64,
    JPEG_BYTES,
    PNG_BASE64,
    PNG_BYTES,
    WEBP_BASE64,
    WEBP_BYTES,
)


class _ErrorWithBody(Exception):
    def __init__(self, message: str, body: dict):
        super().__init__(message)
        self.body = body


class _ErrorWithResponse(Exception):
    def __init__(self, message: str, response_text: str):
        super().__init__(message)
        self.response = SimpleNamespace(text=response_text)


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


def _make_groq_provider(overrides: dict | None = None) -> ProviderGroq:
    provider_config = {
        "id": "test-groq",
        "type": "groq_chat_completion",
        "model": "qwen/qwen3-32b",
        "key": ["test-key"],
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderGroq(
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
async def test_handle_api_error_model_not_vlm_removes_images_and_retries_text_only():
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

        success, *_rest = await provider._handle_api_error(
            Exception("The model is not a VLM and cannot process images"),
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
async def test_handle_api_error_model_not_vlm_after_fallback_raises():
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

        with pytest.raises(Exception, match="not a VLM"):
            await provider._handle_api_error(
                Exception("The model is not a VLM and cannot process images"),
                payloads=payloads,
                context_query=context_query,
                func_tool=None,
                chosen_key="test-key",
                available_api_keys=["test-key"],
                retry_cnt=1,
                max_retries=10,
                image_fallback_used=True,
            )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_with_unserializable_body():
    provider = _make_provider({"image_moderation_error_patterns": ["blocked"]})
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
            {"error": {"message": "blocked"}, "raw": object()},
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


def test_extract_error_text_candidates_truncates_long_response_text():
    long_text = "x" * 20000
    err = _ErrorWithResponse("upstream error", long_text)
    candidates = ProviderOpenAIOfficial._extract_error_text_candidates(err)
    assert candidates
    assert max(len(candidate) for candidate in candidates) <= (
        ProviderOpenAIOfficial._ERROR_TEXT_CANDIDATE_MAX_CHARS
    )


@pytest.mark.asyncio
async def test_openai_payload_keeps_reasoning_content_in_assistant_history():
    provider = _make_provider()
    try:
        payloads = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "think", "think": "step 1"},
                        {"type": "text", "text": "final answer"},
                    ],
                }
            ]
        }

        provider._finally_convert_payload(payloads)

        assistant_message = payloads["messages"][0]
        assert assistant_message["content"] == [{"type": "text", "text": "final answer"}]
        assert assistant_message["reasoning_content"] == "step 1"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_groq_payload_drops_reasoning_content_from_assistant_history():
    provider = _make_groq_provider()
    try:
        payloads = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "think", "think": "step 1"},
                        {"type": "text", "text": "final answer"},
                    ],
                }
            ]
        }

        provider._finally_convert_payload(payloads)

        assistant_message = payloads["messages"][0]
        assert assistant_message["content"] == [{"type": "text", "text": "final answer"}]
        assert "reasoning_content" not in assistant_message
        assert "reasoning" not in assistant_message
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


@pytest.mark.asyncio
async def test_apply_provider_specific_extra_body_overrides_disables_ollama_thinking():
    provider = _make_provider(
        {
            "provider": "ollama",
            "ollama_disable_thinking": True,
        }
    )
    try:
        extra_body = {
            "reasoning": {"effort": "high"},
            "reasoning_effort": "low",
            "think": True,
            "temperature": 0.2,
        }

        provider._apply_provider_specific_extra_body_overrides(extra_body)

        assert extra_body["reasoning_effort"] == "none"
        assert "reasoning" not in extra_body
        assert "think" not in extra_body
        assert extra_body["temperature"] == 0.2
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_injects_reasoning_effort_none_for_ollama(monkeypatch):
    provider = _make_provider(
        {
            "provider": "ollama",
            "ollama_disable_thinking": True,
            "custom_extra_body": {
                "reasoning": {"effort": "high"},
                "temperature": 0.1,
            },
        }
    )
    try:
        captured_kwargs = {}

        async def fake_create(**kwargs):
            captured_kwargs.update(kwargs)
            return ChatCompletion.model_validate(
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "qwen3.5:4b",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "ok",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                }
            )

        monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)

        await provider._query(
            payloads={
                "model": "qwen3.5:4b",
                "messages": [{"role": "user", "content": "hello"}],
            },
            tools=None,
        )

        extra_body = captured_kwargs["extra_body"]
        assert extra_body["reasoning_effort"] == "none"
        assert "reasoning" not in extra_body
        assert extra_body["temperature"] == 0.1
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_encode_image_bs64_detects_base64_mime():
    provider = _make_provider()
    try:
        png_data = await provider.encode_image_bs64(f"base64://{PNG_BASE64}")
        png_data_upper = await provider.encode_image_bs64(f"BASE64://{PNG_BASE64}")
        gif_data = await provider.encode_image_bs64(f"base64://{GIF_BASE64}")
        webp_data = await provider.encode_image_bs64(f"base64://{WEBP_BASE64}")

        assert png_data.startswith("data:image/png;base64,")
        assert png_data_upper.startswith("data:image/png;base64,")
        assert gif_data.startswith("data:image/gif;base64,")
        assert webp_data.startswith("data:image/webp;base64,")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_encode_image_bs64_detects_local_file_mime(tmp_path: Path):
    provider = _make_provider()
    png_path = tmp_path / "pixel.png"
    gif_path = tmp_path / "pixel.gif"
    jpeg_path = tmp_path / "pixel.jpg"
    webp_path = tmp_path / "pixel.webp"
    png_path.write_bytes(PNG_BYTES)
    gif_path.write_bytes(GIF_BYTES)
    jpeg_path.write_bytes(JPEG_BYTES)
    webp_path.write_bytes(WEBP_BYTES)
    try:
        png_data = await provider.encode_image_bs64(str(png_path))
        gif_data = await provider.encode_image_bs64(str(gif_path))
        jpeg_data = await provider.encode_image_bs64(str(jpeg_path))
        webp_data = await provider.encode_image_bs64(str(webp_path))

        assert png_data.startswith("data:image/png;base64,")
        assert gif_data.startswith("data:image/gif;base64,")
        assert jpeg_data.startswith("data:image/jpeg;base64,")
        assert webp_data.startswith("data:image/webp;base64,")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_encode_image_bs64_keeps_data_uri():
    provider = _make_provider()
    png_data_uri = f"data:image/png;base64,{PNG_BASE64}"
    gif_data_uri = f"data:image/gif;base64,{GIF_BASE64}"
    jpeg_data_uri = f"data:image/jpeg;base64,{JPEG_BASE64}"
    try:
        assert await provider.encode_image_bs64(png_data_uri) == png_data_uri
        assert await provider.encode_image_bs64(gif_data_uri) == gif_data_uri
        assert await provider.encode_image_bs64(jpeg_data_uri) == jpeg_data_uri
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_encode_image_bs64_invalid_base64_fallback_to_jpeg():
    provider = _make_provider()
    try:
        image_data = await provider.encode_image_bs64("base64://not-valid-base64")
        assert image_data == "data:image/jpeg;base64,not-valid-base64"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_encode_image_bs64_rejects_non_image_data_uri():
    provider = _make_provider()
    try:
        with pytest.raises(ValueError, match="Only image data URI is supported"):
            await provider.encode_image_bs64("data:text/plain;base64,SGVsbG8=")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_encode_image_bs64_rejects_unsupported_uri_scheme():
    provider = _make_provider()
    try:
        with pytest.raises(ValueError, match="Unsupported image source scheme"):
            await provider.encode_image_bs64("s3://bucket/path/image.png")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_assemble_context_extra_image_file_uri_mime(tmp_path: Path):
    provider = _make_provider()
    png_path = tmp_path / "agent-request.png"
    png_path.write_bytes(PNG_BYTES)
    try:
        assembled = await provider.assemble_context(
            text="hello",
            extra_user_content_parts=[
                ImageURLPart(
                    image_url=ImageURLPart.ImageURL(
                        url=f"file:///{png_path.as_posix()}",
                    )
                )
            ],
        )

        assert isinstance(assembled["content"], list)
        image_part = assembled["content"][1]
        assert image_part["type"] == "image_url"
        assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_assemble_context_uppercase_https_image_url(
    tmp_path: Path, monkeypatch
):
    provider = _make_provider()
    png_path = tmp_path / "remote.png"
    png_path.write_bytes(PNG_BYTES)

    async def fake_download(url: str) -> str:
        assert url == "HTTPS://example.com/asset.png"
        return str(png_path)

    monkeypatch.setattr(
        "astrbot.core.provider.sources.openai_source.download_image_by_url",
        fake_download,
    )
    try:
        assembled = await provider.assemble_context(
            text="hello",
            image_urls=["HTTPS://example.com/asset.png"],
        )

        image_part = next(
            part for part in assembled["content"] if part.get("type") == "image_url"
        )
        assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    finally:
        await provider.terminate()
