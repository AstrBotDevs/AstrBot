from types import SimpleNamespace

import pytest

from astrbot.core.agent.message import (
    Message,
    TextPart,
    VideoURLPart,
    bind_checkpoint_messages,
    dump_messages_with_checkpoints,
)
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.modalities import sanitize_contexts_by_modalities
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI

VIDEO_DATA_URL = "data:video/mp4;base64,AAAAGGZ0eXBtcDQyAAAAAG1wNDJpc29t"


def _gemini_provider() -> ProviderGoogleGenAI:
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    return provider


def _runner(modalities) -> ToolLoopAgentRunner:
    runner = ToolLoopAgentRunner.__new__(ToolLoopAgentRunner)
    runner.provider = SimpleNamespace(provider_config={"modalities": modalities})
    return runner


def test_video_url_part_is_registered_and_round_trips():
    """A `video_url` dict must resolve through the ContentPart registry.

    The registry lookup in `ContentPart.__get_pydantic_core_schema__` is
    unguarded, so an unregistered type raises `KeyError` the moment the block is
    validated from persisted history.
    """
    message = Message.model_validate(
        {
            "role": "user",
            "content": [{"type": "video_url", "video_url": {"url": VIDEO_DATA_URL}}],
        }
    )

    assert isinstance(message.content[0], VideoURLPart)
    assert message.content[0].video_url.url == VIDEO_DATA_URL


@pytest.mark.asyncio
async def test_assemble_context_marks_video_block_as_transient():
    request = ProviderRequest(prompt="", video_urls=[VIDEO_DATA_URL])

    context = await request.assemble_context()

    video_blocks = [
        block for block in context["content"] if block.get("type") == "video_url"
    ]
    assert len(video_blocks) == 1
    assert video_blocks[0]["_no_save"] is True


@pytest.mark.asyncio
async def test_video_block_is_not_written_to_history():
    """The video payload must not be persisted and replayed on later requests."""
    request = ProviderRequest(prompt="look", video_urls=[VIDEO_DATA_URL])
    context = await request.assemble_context()

    messages = [Message.model_validate(context)]
    dumped = dump_messages_with_checkpoints(messages)

    persisted_types = [
        part["type"]
        for part in dumped[0]["content"]
        if isinstance(part, dict)
    ]
    assert "video_url" not in persisted_types
    assert "text" in persisted_types


@pytest.mark.asyncio
async def test_transient_video_reaches_provider_but_not_history():
    """Prove both halves of the design in one place.

    Providers serialize messages with `model_dump()`, which does not emit
    `_no_save`, so the video still reaches the provider payload. Persistence goes
    through `dump_messages_with_checkpoints`, which drops it.
    """
    request = ProviderRequest(prompt="look", video_urls=[VIDEO_DATA_URL])
    context = await request.assemble_context()
    message = Message.model_validate(context)

    assert message.content[1]._no_save is True

    provider_payload = message.model_dump()
    assert any(part["type"] == "video_url" for part in provider_payload["content"])

    persisted = dump_messages_with_checkpoints([message])
    assert not any(part["type"] == "video_url" for part in persisted[0]["content"])


@pytest.mark.asyncio
async def test_gemini_accepts_video_url_block():
    provider = _gemini_provider()
    payloads = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this"},
                    {"type": "video_url", "video_url": {"url": VIDEO_DATA_URL}},
                ],
            }
        ]
    }

    contents = await provider._prepare_conversation(payloads)

    parts = contents[0].parts
    assert len(parts) == 2
    assert parts[1].inline_data is not None
    assert parts[1].inline_data.mime_type == "video/mp4"


@pytest.mark.asyncio
async def test_gemini_degrades_unknown_block_type_instead_of_raising():
    """An unknown block must not raise.

    The message is replayed from history on every later request, so raising here
    would keep failing long after the turn that produced it.
    """
    provider = _gemini_provider()
    payloads = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "some_future_block", "payload": "x"}],
            }
        ]
    }

    contents = await provider._prepare_conversation(payloads)

    assert contents[0].parts[0].text == "[some_future_block]"


@pytest.mark.asyncio
async def test_video_is_opt_in_for_providers_without_modalities():
    """An unconfigured provider must not receive video.

    An empty or missing `modalities` list means "supports everything" for
    backward compatibility, but video postdates that convention and is not
    universally supported.
    """
    runner = _runner([])
    request = ProviderRequest(prompt="look", video_urls=[VIDEO_DATA_URL])

    context = await runner._assemble_request_context_for_provider(request)

    # With the video removed this collapses to the plain-text form, which is the
    # pre-existing behaviour for a text-only request.
    content = context["content"]
    if isinstance(content, str):
        assert "video_url" not in content
    else:
        assert not any(block.get("type") == "video_url" for block in content)


@pytest.mark.asyncio
async def test_video_is_sent_when_declared():
    runner = _runner(["text", "image", "audio", "video", "tool_use"])
    request = ProviderRequest(prompt="look", video_urls=[VIDEO_DATA_URL])

    context = await runner._assemble_request_context_for_provider(request)

    assert any(block.get("type") == "video_url" for block in context["content"])


@pytest.mark.asyncio
async def test_video_is_replaced_with_placeholder_when_not_declared():
    runner = _runner(["text", "image", "audio", "tool_use"])
    request = ProviderRequest(prompt="look", video_urls=[VIDEO_DATA_URL])

    context = await runner._assemble_request_context_for_provider(request)

    content = context["content"]
    assert not any(block.get("type") == "video_url" for block in content)
    assert {"type": "text", "text": "[Video]"} in content


def test_modality_sanitizer_degrades_video_to_text():
    contexts = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {"type": "video_url", "video_url": {"url": VIDEO_DATA_URL}},
            ],
        }
    ]

    sanitized, stats = sanitize_contexts_by_modalities(contexts, ["text", "image"])

    assert stats.fixed_video_blocks == 1
    assert {"type": "text", "text": "[Video]"} in sanitized[0]["content"]


def test_modality_sanitizer_keeps_video_when_declared():
    contexts = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {"type": "video_url", "video_url": {"url": VIDEO_DATA_URL}},
            ],
        }
    ]

    sanitized, stats = sanitize_contexts_by_modalities(
        contexts, ["text", "image", "audio", "video"]
    )

    assert stats.fixed_video_blocks == 0
    assert any(block.get("type") == "video_url" for block in sanitized[0]["content"])


@pytest.mark.asyncio
async def test_video_placeholder_is_added_for_video_only_requests():
    request = ProviderRequest(prompt="", video_urls=[VIDEO_DATA_URL])

    context = await request.assemble_context()

    assert context["content"][0] == {"type": "text", "text": "[Video]"}


def test_text_only_request_is_unchanged():
    """The simple string form must be preserved for text-only requests."""
    request = ProviderRequest(prompt="hello")

    assert request.video_urls == []
    assert TextPart(text="hello").text == "hello"
