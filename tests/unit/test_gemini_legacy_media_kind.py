"""Tests for media family detection on the legacy Gemini request path.

``ProviderGoogleGenAI.text_chat(prompt=...)`` assembles the user message with
``assemble_context``. Its audio slot is also the only media channel some callers
expose, so a video can arrive there as a ``data:video/mp4`` payload or as a saved
``.mp4`` path. Resolving such a reference as audio re-encodes it to WAV, which
keeps the soundtrack and silently drops the picture.
"""

import base64
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.agent.message import AudioURLPart
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.utils.media_utils import (
    ResolvedMediaData,
    looks_like_video_media_ref,
)

VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
VIDEO_DATA_URL = f"data:video/mp4;base64,{base64.b64encode(VIDEO_BYTES).decode()}"
AUDIO_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt "
AUDIO_DATA_URL = f"data:audio/wav;base64,{base64.b64encode(AUDIO_BYTES).decode()}"
RESOLVER = (
    "astrbot.core.provider.sources.gemini_source.resolve_media_ref_to_base64_data"
)


def _provider() -> ProviderGoogleGenAI:
    """Build the provider without running its network setup."""
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    return provider


def _content_blocks(context: dict) -> list[dict]:
    """Return the assembled message as a list of content blocks."""
    content = context["content"]
    if isinstance(content, list):
        return content
    return [{"type": "text", "text": content}]


@pytest.mark.asyncio
async def test_video_data_uri_in_the_audio_slot_reaches_gemini_as_video():
    """The picture must survive instead of being transcoded to audio."""
    provider = _provider()

    context = await provider.assemble_context("look", audio_urls=[VIDEO_DATA_URL])

    assert [block["type"] for block in _content_blocks(context)] == [
        "text",
        "video_url",
    ]

    contents = await provider._prepare_conversation({"messages": [context]})
    video_part = contents[0].parts[1]
    assert video_part.inline_data.mime_type == "video/mp4"
    assert video_part.inline_data.data == VIDEO_BYTES


@pytest.mark.asyncio
async def test_extra_audio_part_carrying_video_stays_video():
    """An `audio_url` extra part whose payload is a video keeps its frames."""
    provider = _provider()
    part = AudioURLPart(audio_url=AudioURLPart.AudioURL(url=VIDEO_DATA_URL))

    context = await provider.assemble_context("look", extra_user_content_parts=[part])

    assert [block["type"] for block in _content_blocks(context)] == [
        "text",
        "video_url",
    ]

    contents = await provider._prepare_conversation({"messages": [context]})
    assert contents[0].parts[1].inline_data.mime_type == "video/mp4"


@pytest.mark.asyncio
async def test_local_video_path_skips_the_audio_converter(tmp_path):
    """A saved `.mp4` must be resolved as video, never through the WAV branch."""
    provider = _provider()
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(VIDEO_BYTES)
    resolve = AsyncMock(
        return_value=ResolvedMediaData(
            base64_data=base64.b64encode(VIDEO_BYTES).decode(),
            mime_type="video/mp4",
        )
    )

    with patch(RESOLVER, resolve):
        context = await provider.assemble_context("look", audio_urls=[str(video_path)])

    assert [call.kwargs["media_type"] for call in resolve.await_args_list] == ["video"]
    assert [block["type"] for block in _content_blocks(context)] == [
        "text",
        "video_url",
    ]


@pytest.mark.asyncio
async def test_unresolvable_video_degrades_to_a_placeholder(tmp_path):
    """A video the provider cannot read must not vanish without a trace."""
    provider = _provider()
    video_path = tmp_path / "broken.mp4"
    video_path.write_bytes(b"not a video")

    with patch(RESOLVER, AsyncMock(return_value=None)):
        context = await provider.assemble_context("look", audio_urls=[str(video_path)])

    assert {"type": "text", "text": "[Video]"} in _content_blocks(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("audio_ref", ["voice.wav", "data:audio/wav;base64,AAAA"])
async def test_audio_reference_keeps_the_audio_path(audio_ref):
    """Regression: genuine audio still resolves through the WAV branch."""
    provider = _provider()
    resolve = AsyncMock(
        return_value=ResolvedMediaData(
            base64_data=base64.b64encode(AUDIO_BYTES).decode(),
            mime_type="audio/wav",
        )
    )

    with patch(RESOLVER, resolve):
        context = await provider.assemble_context("look", audio_urls=[audio_ref])

    assert [call.kwargs["media_type"] for call in resolve.await_args_list] == ["audio"]
    assert _content_blocks(context)[1] == {
        "type": "audio_url",
        "audio_url": {"url": AUDIO_DATA_URL},
    }


@pytest.mark.parametrize(
    "media_ref",
    [
        VIDEO_DATA_URL,
        "clip.mp4",
        "C:\\media\\clip.MOV",
        "https://cdn.example.com/v/clip.webm?token=secret",
        "file:///tmp/clip.mkv",
    ],
)
def test_video_references_are_recognised(media_ref):
    """Declared MIME types and video containers are detected."""
    assert looks_like_video_media_ref(media_ref) is True


@pytest.mark.parametrize(
    "media_ref",
    [
        AUDIO_DATA_URL,
        "voice.wav",
        "C:\\media\\voice.m4a",
        "https://cdn.example.com/a/track.mp3?token=secret",
        "base64://AAAA",
        "",
        None,
    ],
)
def test_non_video_references_keep_their_declared_family(media_ref):
    """Audio and undecidable references stay on the audio path."""
    assert looks_like_video_media_ref(media_ref) is False
