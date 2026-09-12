import pytest

from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.modalities import (
    sanitize_contexts_by_modalities,
)
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.utils.media_utils import ResolvedMediaData


@pytest.mark.asyncio
async def test_assemble_context_includes_video_url_block(monkeypatch):
    """ProviderRequest.assemble_context must emit a video_url content block."""
    captured = {}

    class _FakeVideoData:
        def __init__(self, data, mime_type):
            self.base64_data = data
            self.mime_type = mime_type
            self.format = "mp4"

        def to_data_url(self):
            return f"data:{self.mime_type};base64,{self.base64_data}"

    async def fake_to_base64_data(
        self,
        *,
        strict=False,
        target_format=None,
        preserve_mp3=False,
        default_mime_type=None,
    ):
        captured["media_type"] = self.media_type
        return _FakeVideoData("abcd", "video/mp4")

    monkeypatch.setattr(
        "astrbot.core.provider.entities.MediaResolver.to_base64_data",
        fake_to_base64_data,
    )

    req = ProviderRequest(prompt="look", video_urls=["https://example.com/clip.mp4"])
    msg = await req.assemble_context()

    assert msg["role"] == "user"
    blocks = msg["content"]
    assert blocks[0] == {"type": "text", "text": "look"}
    assert blocks[1] == {
        "type": "video_url",
        "video_url": {"url": "data:video/mp4;base64,abcd"},
    }
    assert captured["media_type"] == "video"


def test_sanitize_contexts_strips_video_when_unsupported():
    contexts = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi"},
                {
                    "type": "video_url",
                    "video_url": {"url": "data:video/mp4;base64,abcd"},
                },
            ],
        }
    ]
    sanitized, stats = sanitize_contexts_by_modalities(
        contexts, ["text", "image", "audio", "tool_use"]
    )
    assert sanitized[0]["content"] == [
        {"type": "text", "text": "hi"},
        {"type": "text", "text": "[Video]"},
    ]
    assert stats.fixed_video_blocks == 1


def test_sanitize_contexts_preserves_video_when_supported():
    block = {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,abcd"}}
    contexts = [{"role": "user", "content": [{"type": "text", "text": "hi"}, block]}]
    sanitized, stats = sanitize_contexts_by_modalities(
        contexts, ["text", "image", "audio", "video", "tool_use"]
    )
    assert sanitized[0]["content"][1] == block
    assert stats.fixed_video_blocks == 0


@pytest.mark.asyncio
async def test_prepare_chat_payload_materializes_context_video_urls(monkeypatch):
    """The OpenAI source resolves video_url context blocks into data URLs."""
    import astrbot.core.provider.sources.openai_source as openai_source_module

    async def fake_resolve_media_ref_to_base64_data(
        media_ref, *, media_type, strict=False
    ):
        assert media_type == "video"
        return ResolvedMediaData(base64_data="abcd", mime_type="video/mp4")

    monkeypatch.setattr(
        openai_source_module,
        "resolve_media_ref_to_base64_data",
        fake_resolve_media_ref_to_base64_data,
    )

    provider = ProviderOpenAIOfficial(
        provider_config={
            "id": "test-openai",
            "type": "openai_chat_completion",
            "model": "gpt-4o-mini",
            "key": ["test-key"],
        },
        provider_settings={},
    )
    try:
        contexts = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look"},
                    {
                        "type": "video_url",
                        "video_url": {"url": "https://example.com/clip.mp4"},
                    },
                ],
            }
        ]
        payloads, _ = await provider._prepare_chat_payload(
            prompt=None, contexts=contexts
        )
        assert payloads["messages"][0]["content"] == [
            {"type": "text", "text": "look"},
            {
                "type": "video_url",
                "video_url": {"url": "data:video/mp4;base64,abcd"},
            },
        ]
    finally:
        await provider.terminate()


def test_anthropic_prepare_payload_converts_video_url_to_anthropic_video_block():
    """The Anthropic source must convert video_url blocks into Anthropic video blocks."""
    from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

    provider = ProviderAnthropic(
        provider_config={
            "id": "test-anthropic",
            "type": "anthropic_chat_completion",
            "model": "MiniMax-M3",
            "key": ["test-key"],
            "api_base": "https://api.minimaxi.com/anthropic",
        },
        provider_settings={},
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe this clip"},
                {
                    "type": "video_url",
                    "video_url": {"url": "data:video/mp4;base64,abcd"},
                },
            ],
        }
    ]
    _, new_messages = provider._prepare_payload(messages)
    user_blocks = new_messages[0]["content"]
    assert user_blocks[0] == {"type": "text", "text": "describe this clip"}
    assert user_blocks[1] == {
        "type": "video",
        "source": {
            "type": "base64",
            "media_type": "video/mp4",
            "data": "abcd",
        },
    }
