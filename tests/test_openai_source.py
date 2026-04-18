from types import SimpleNamespace

import pytest
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from PIL import Image as PILImage

from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.sources.groq_source import ProviderGroq
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


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
        assert assistant_message["content"] == [
            {"type": "text", "text": "final answer"}
        ]
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
        assert assistant_message["content"] == [
            {"type": "text", "text": "final answer"}
        ]
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
async def test_handle_api_error_invalid_attachment_removes_images_and_retries_text_only():
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
        err = _ErrorWithBody(
            "upstream error",
            {
                "error": {
                    "code": "INVALID_ATTACHMENT",
                    "message": "download attachment: unexpected status 404",
                }
            },
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
async def test_handle_api_error_invalid_attachment_without_images_raises():
    provider = _make_provider()
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
        err = _ErrorWithBody(
            "upstream error",
            {
                "error": {
                    "code": "INVALID_ATTACHMENT",
                    "message": "download attachment: unexpected status 404",
                }
            },
        )

        with pytest.raises(_ErrorWithBody, match="upstream error"):
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
async def test_handle_api_error_invalid_attachment_after_fallback_raises():
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
        err = _ErrorWithBody(
            "upstream error",
            {
                "error": {
                    "code": "INVALID_ATTACHMENT",
                    "message": "download attachment: unexpected status 404",
                }
            },
        )

        with pytest.raises(_ErrorWithBody, match="upstream error"):
            await provider._handle_api_error(
                err,
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
async def test_prepare_chat_payload_materializes_context_http_image_urls(monkeypatch):
    provider = _make_provider()
    try:

        async def fake_download(url: str) -> str:
            assert url == "https://example.com/quoted.png"
            return "/tmp/quoted.png"

        def fake_encode(image_path: str, **_kwargs) -> str:
            assert image_path == "/tmp/quoted.png"
            return "data:image/png;base64,abcd"

        monkeypatch.setattr(
            "astrbot.core.provider.sources.openai_source.download_image_by_url",
            fake_download,
        )
        monkeypatch.setattr(provider, "_encode_image_file_to_data_url", fake_encode)

        contexts = [
            {
                "role": "user",
                "metadata": {"source": "quoted"},
                "content": [
                    {"type": "text", "text": "look"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "https://example.com/quoted.png",
                            "id": "ctx-img",
                            "detail": "high",
                        },
                    },
                ],
            }
        ]

        payloads, _ = await provider._prepare_chat_payload(
            prompt=None,
            contexts=contexts,
        )

        assert payloads["messages"][0]["content"] == [
            {"type": "text", "text": "look"},
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,abcd",
                    "detail": "high",
                },
            },
        ]
        assert payloads["messages"][0]["content"][1]["image_url"].get("id") is None
        assert contexts[0]["content"][1]["image_url"] == {
            "url": "https://example.com/quoted.png",
            "id": "ctx-img",
            "detail": "high",
        }
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_prepare_chat_payload_skips_materialization_for_text_only_context(
    monkeypatch,
):
    provider = _make_provider()
    try:

        async def fail_if_called(_context_query):
            raise AssertionError("materialization should be skipped")

        monkeypatch.setattr(
            provider, "_materialize_context_image_parts", fail_if_called
        )

        payloads, _ = await provider._prepare_chat_payload(
            prompt=None,
            contexts=[{"role": "user", "content": "hello"}],
        )

        assert payloads["messages"] == [{"role": "user", "content": "hello"}]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_prepare_chat_payload_skips_materialization_for_text_only_parts(
    monkeypatch,
):
    provider = _make_provider()
    try:

        async def fail_if_called(_context_query):
            raise AssertionError("materialization should be skipped")

        monkeypatch.setattr(
            provider, "_materialize_context_image_parts", fail_if_called
        )

        payloads, _ = await provider._prepare_chat_payload(
            prompt=None,
            contexts=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "hello"}],
                }
            ],
        )

        assert payloads["messages"] == [
            {
                "role": "user",
                "content": [{"type": "text", "text": "hello"}],
            }
        ]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_prepare_chat_payload_materializes_context_http_image_urls_with_detected_mime(
    monkeypatch, tmp_path
):
    provider = _make_provider()
    try:
        image_path = tmp_path / "quoted-image.png"
        PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_path)

        async def fake_download(url: str) -> str:
            assert url == "https://example.com/quoted.png"
            return str(image_path)

        monkeypatch.setattr(
            "astrbot.core.provider.sources.openai_source.download_image_by_url",
            fake_download,
        )

        payloads, _ = await provider._prepare_chat_payload(
            prompt=None,
            contexts=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "look"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://example.com/quoted.png",
                            },
                        },
                    ],
                }
            ],
        )

        image_payload = payloads["messages"][0]["content"][1]["image_url"]
        assert image_payload["url"].startswith("data:image/png;base64,")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_prepare_chat_payload_materializes_context_file_uri_image_urls(tmp_path):
    provider = _make_provider()
    try:
        image_path = tmp_path / "quoted-image.png"
        PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_path)

        payloads, _ = await provider._prepare_chat_payload(
            prompt=None,
            contexts=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "look"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_path.as_uri(),
                            },
                        },
                    ],
                }
            ],
        )

        image_payload = payloads["messages"][0]["content"][1]["image_url"]
        assert image_payload["url"].startswith("data:image/png;base64,")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_file_uri_to_path_preserves_windows_drive_letter():
    provider = _make_provider()
    try:
        assert provider._file_uri_to_path("file:///C:/tmp/quoted-image.png") == (
            "C:/tmp/quoted-image.png"
        )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_file_uri_to_path_preserves_windows_netloc_drive_letter():
    provider = _make_provider()
    try:
        assert provider._file_uri_to_path("file://C:/tmp/quoted-image.png") == (
            "C:/tmp/quoted-image.png"
        )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_file_uri_to_path_preserves_remote_netloc_as_unc_path():
    provider = _make_provider()
    try:
        assert provider._file_uri_to_path("file://server/share/quoted-image.png") == (
            "//server/share/quoted-image.png"
        )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_resolve_image_part_rejects_invalid_local_file(tmp_path):
    provider = _make_provider()
    try:
        invalid_file = tmp_path / "not-image.txt"
        invalid_file.write_text("not an image")

        assert await provider._resolve_image_part(str(invalid_file)) is None
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_resolve_image_part_rejects_invalid_file_uri(tmp_path):
    provider = _make_provider()
    try:
        invalid_file = tmp_path / "not-image.txt"
        invalid_file.write_text("not an image")

        assert await provider._resolve_image_part(invalid_file.as_uri()) is None
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_image_ref_to_data_url_mode_controls_invalid_file_behavior(tmp_path):
    provider = _make_provider()
    try:
        invalid_file = tmp_path / "not-image.txt"
        invalid_file.write_text("not an image")

        assert (
            await provider._image_ref_to_data_url(str(invalid_file), mode="safe")
            is None
        )
        with pytest.raises(ValueError, match="Invalid image file"):
            await provider._image_ref_to_data_url(str(invalid_file), mode="strict")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_materialize_context_image_parts_returns_new_messages(monkeypatch):
    provider = _make_provider()
    try:
        context_query = [
            {
                "role": "user",
                "metadata": {"source": "quoted"},
                "content": [
                    {"type": "text", "text": "look"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "https://example.com/quoted.png",
                            "detail": "high",
                        },
                    },
                ],
            },
            {"role": "assistant", "content": "plain text"},
        ]

        async def fake_resolve(image_url: str, *, image_detail: str | None = None):
            assert image_url == "https://example.com/quoted.png"
            assert image_detail == "high"
            return {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,abcd",
                    "detail": "high",
                },
            }

        monkeypatch.setattr(provider, "_resolve_image_part", fake_resolve)

        materialized = await provider._materialize_context_image_parts(context_query)

        assert materialized is not context_query
        assert materialized[0] is not context_query[0]
        assert materialized[0]["metadata"] is context_query[0]["metadata"]
        assert materialized[0]["content"][0] is context_query[0]["content"][0]
        assert (
            materialized[0]["content"][1]["image_url"]["url"]
            == "data:image/png;base64,abcd"
        )
        assert (
            context_query[0]["content"][1]["image_url"]["url"]
            == "https://example.com/quoted.png"
        )
        assert materialized[1] is not context_query[1]
        assert materialized[1]["content"] == "plain text"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_encode_image_bs64_missing_file_raises(tmp_path):
    provider = _make_provider()
    try:
        missing_path = tmp_path / "missing-image.png"
        with pytest.raises(FileNotFoundError):
            await provider.encode_image_bs64(str(missing_path))
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_encode_image_bs64_invalid_file_raises(tmp_path):
    provider = _make_provider()
    try:
        invalid_file = tmp_path / "not-image.txt"
        invalid_file.write_text("not an image")

        with pytest.raises(ValueError, match="Invalid image file"):
            await provider.encode_image_bs64(str(invalid_file))
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_encode_image_bs64_supports_base64_scheme():
    provider = _make_provider()
    try:
        image_data = await provider.encode_image_bs64("base64://abcd")

        assert image_data == "data:image/jpeg;base64,abcd"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_encode_image_bs64_supports_file_uri(tmp_path):
    provider = _make_provider()
    try:
        image_path = tmp_path / "quoted-image.png"
        PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_path)

        image_data = await provider.encode_image_bs64(image_path.as_uri())

        assert image_data.startswith("data:image/png;base64,")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_resolve_image_part_supports_base64_scheme():
    provider = _make_provider()
    try:
        assert await provider._resolve_image_part("base64://abcd") == {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,abcd"},
        }
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_prepare_chat_payload_materializes_context_localhost_file_uri_image_urls(
    tmp_path,
):
    provider = _make_provider()
    try:
        image_path = tmp_path / "quoted-image.png"
        PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_path)

        localhost_uri = f"file://localhost{image_path.as_posix()}"
        payloads, _ = await provider._prepare_chat_payload(
            prompt=None,
            contexts=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "look"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": localhost_uri,
                            },
                        },
                    ],
                }
            ],
        )

        image_payload = payloads["messages"][0]["content"][1]["image_url"]
        assert image_payload["url"].startswith("data:image/png;base64,")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_prepare_chat_payload_keeps_original_context_image_when_materialization_fails(
    monkeypatch,
):
    provider = _make_provider()
    try:

        async def fake_download(url: str) -> str:
            assert url == "https://example.com/expired.png"
            return "/tmp/not-an-image"

        monkeypatch.setattr(
            "astrbot.core.provider.sources.openai_source.download_image_by_url",
            fake_download,
        )
        monkeypatch.setattr(
            provider,
            "_encode_image_file_to_data_url",
            lambda _image_path, **_kwargs: None,
        )

        payloads, _ = await provider._prepare_chat_payload(
            prompt=None,
            contexts=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "look"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://example.com/expired.png",
                            },
                        },
                    ],
                }
            ],
        )

        assert payloads["messages"][0]["content"] == [
            {"type": "text", "text": "look"},
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://example.com/expired.png",
                },
            },
        ]
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
async def test_parse_openai_completion_raises_empty_model_output_error():
    provider = _make_provider()
    try:
        completion = ChatCompletion.model_validate(
            {
                "id": "chatcmpl-empty",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "refusal": None,
                            "tool_calls": None,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 0,
                    "total_tokens": 1,
                },
            }
        )

        with pytest.raises(EmptyModelOutputError):
            await provider._parse_openai_completion(completion, tools=None)
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_stream_extracts_usage_from_empty_choices_chunk(monkeypatch):
    provider = _make_provider()
    try:
        chunks = [
            ChatCompletionChunk.model_validate(
                {
                    "id": "chatcmpl-stream",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "gpt-4o-mini",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "content": "ok",
                            },
                            "finish_reason": None,
                        }
                    ],
                }
            ),
            ChatCompletionChunk.model_validate(
                {
                    "id": "chatcmpl-stream",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "gpt-4o-mini",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop",
                        }
                    ],
                }
            ),
            ChatCompletionChunk.model_validate(
                {
                    "id": "chatcmpl-stream",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "gpt-4o-mini",
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 2550,
                        "completion_tokens": 125,
                        "total_tokens": 2675,
                        "prompt_tokens_details": {
                            "cached_tokens": 2488,
                        },
                    },
                }
            ),
        ]

        async def fake_stream():
            for chunk in chunks:
                yield chunk

        async def fake_create(**kwargs):
            return fake_stream()

        monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)

        responses = [
            response
            async for response in provider._query_stream(
                payloads={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                tools=None,
            )
        ]

        final_response = responses[-1]
        assert final_response.completion_text == "ok"
        assert final_response.usage is not None
        assert final_response.usage.input_other == 62
        assert final_response.usage.input_cached == 2488
        assert final_response.usage.output == 125
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_filters_empty_assistant_message_without_tool_calls(monkeypatch):
    """Test that empty assistant messages without tool_calls are filtered out."""
    provider = _make_provider()
    try:
        captured_kwargs = {}

        async def fake_create(**kwargs):
            captured_kwargs.update(kwargs)
            return ChatCompletion.model_validate(
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "gpt-4o-mini",
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

        payloads = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": ""},  # Should be filtered
                {"role": "user", "content": "world"},
            ],
        }

        await provider._query(payloads=payloads, tools=None)

        # The empty assistant message should be filtered out
        messages = captured_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0] == {"role": "user", "content": "hello"}
        assert messages[1] == {"role": "user", "content": "world"}
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_filters_null_content_assistant_message_without_tool_calls(
    monkeypatch,
):
    """Test that assistant messages with null content and no tool_calls are filtered."""
    provider = _make_provider()
    try:
        captured_kwargs = {}

        async def fake_create(**kwargs):
            captured_kwargs.update(kwargs)
            return ChatCompletion.model_validate(
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "gpt-4o-mini",
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

        payloads = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": None},  # Should be filtered
                {"role": "user", "content": "world"},
            ],
        }

        await provider._query(payloads=payloads, tools=None)

        # The null content assistant message should be filtered out
        messages = captured_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0] == {"role": "user", "content": "hello"}
        assert messages[1] == {"role": "user", "content": "world"}
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_converts_empty_content_to_none_with_tool_calls(monkeypatch):
    """Test that empty content with tool_calls is converted to None (OpenAI spec)."""
    provider = _make_provider()
    try:
        captured_kwargs = {}

        async def fake_create(**kwargs):
            captured_kwargs.update(kwargs)
            return ChatCompletion.model_validate(
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "gpt-4o-mini",
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

        payloads = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": "hello"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-123",
                            "type": "function",
                            "function": {"name": "test", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "user", "content": "world"},
            ],
        }

        await provider._query(payloads=payloads, tools=None)

        # The assistant message with tool_calls should be kept but content set to None
        messages = captured_kwargs["messages"]
        assert len(messages) == 3
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] is None
        assert messages[1]["tool_calls"] is not None
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_keeps_valid_assistant_message_with_content(monkeypatch):
    """Test that valid assistant messages with content are kept."""
    provider = _make_provider()
    try:
        captured_kwargs = {}

        async def fake_create(**kwargs):
            captured_kwargs.update(kwargs)
            return ChatCompletion.model_validate(
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "gpt-4o-mini",
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

        payloads = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "response"},
                {"role": "user", "content": "world"},
            ],
        }

        await provider._query(payloads=payloads, tools=None)

        # All messages should be kept
        messages = captured_kwargs["messages"]
        assert len(messages) == 3
        assert messages[1] == {"role": "assistant", "content": "response"}
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_keeps_assistant_message_with_tool_calls_and_none_content(
    monkeypatch,
):
    """Test that assistant messages with tool_calls and None content are kept."""
    provider = _make_provider()
    try:
        captured_kwargs = {}

        async def fake_create(**kwargs):
            captured_kwargs.update(kwargs)
            return ChatCompletion.model_validate(
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "gpt-4o-mini",
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

        payloads = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": "hello"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-123",
                            "type": "function",
                            "function": {"name": "test", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "user", "content": "world"},
            ],
        }

        await provider._query(payloads=payloads, tools=None)

        # The assistant message with tool_calls should be kept
        messages = captured_kwargs["messages"]
        assert len(messages) == 3
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] is None
        assert messages[1]["tool_calls"] is not None
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_does_not_filter_user_or_system_messages(monkeypatch):
    """Test that user and system messages are not affected by the filter."""
    provider = _make_provider()
    try:
        captured_kwargs = {}

        async def fake_create(**kwargs):
            captured_kwargs.update(kwargs)
            return ChatCompletion.model_validate(
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "gpt-4o-mini",
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

        payloads = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": ""},  # Empty system message
                {"role": "user", "content": ""},  # Empty user message
                {"role": "assistant", "content": ""},  # Should be filtered
                {"role": "user", "content": "hello"},
            ],
        }

        await provider._query(payloads=payloads, tools=None)

        # Only assistant message should be filtered
        messages = captured_kwargs["messages"]
        assert len(messages) == 3
        assert messages[0] == {"role": "system", "content": ""}
        assert messages[1] == {"role": "user", "content": ""}
        assert messages[2] == {"role": "user", "content": "hello"}
    finally:
        await provider.terminate()
