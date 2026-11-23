import wave
from types import SimpleNamespace

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Record
from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter
from astrbot.core.platform.sources.line.line_adapter import LinePlatformAdapter
from astrbot.core.platform.sources.misskey.misskey_utils import create_file_component
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)
from astrbot.core.utils.media_utils import MediaResolver


@pytest.fixture
def media_resolution(monkeypatch, tmp_path):
    """Keep real resolver construction and isolate the media conversion boundary."""
    destination = tmp_path / "resolved.wav"
    with wave.open(str(destination), "wb") as output:
        output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        output.writeframes(b"\x00\x00" * 80)
    calls = []

    async def resolve(resolver, **kwargs) -> str:
        assert isinstance(resolver, MediaResolver)
        calls.append(
            (
                resolver.media_ref,
                {
                    "media_type": resolver.media_type,
                    "default_suffix": resolver.default_suffix,
                },
                kwargs,
            )
        )
        return str(destination)

    monkeypatch.setattr(MediaResolver, "to_path", resolve)
    return SimpleNamespace(path=str(destination), calls=calls)


@pytest.mark.asyncio
async def test_line_audio_component_defers_external_conversion_to_preprocess(
    media_resolution,
):
    adapter = LinePlatformAdapter.__new__(LinePlatformAdapter)

    record = await adapter._build_audio_component(
        "msg-1",
        {
            "contentProvider": {
                "type": "external",
                "originalContentUrl": "https://example.test/voice.m4a",
            }
        },
    )

    assert isinstance(record, Record)
    assert record.file == "https://example.test/voice.m4a"
    assert record.url == "https://example.test/voice.m4a"
    assert media_resolution.calls == []


@pytest.mark.asyncio
async def test_lark_audio_component_retains_download_for_event_cleanup(
    monkeypatch,
    tmp_path,
    media_resolution,
):
    adapter = LarkPlatformAdapter.__new__(LarkPlatformAdapter)
    source = tmp_path / "lark-source.opus"

    async def download_resource(**kwargs):
        assert kwargs["message_type"] == "audio"
        assert kwargs["message_id"] == "msg-1"
        source.write_bytes(b"downloaded-audio-payload")
        return str(source)

    monkeypatch.setattr(adapter, "_download_file_resource_to_temp", download_resource)

    records = await adapter._parse_message_components(
        message_id="msg-1",
        message_type="audio",
        content={"file_key": "file-key"},
        at_map={},
    )

    assert len(records) == 1
    assert isinstance(records[0], Record)
    assert records[0].file == str(source)
    assert records[0].url == str(source)
    assert source.read_bytes() == b"downloaded-audio-payload"
    assert media_resolution.calls == []


@pytest.mark.asyncio
async def test_qqofficial_audio_attachment_defers_conversion_to_preprocess(
    media_resolution,
):
    record = await QQOfficialPlatformAdapter._prepare_audio_attachment(
        "https://example.test/voice.amr",
        "voice.amr",
    )

    assert isinstance(record, Record)
    assert record.file == "https://example.test/voice.amr"
    assert record.url == "https://example.test/voice.amr"
    assert media_resolution.calls == []


@pytest.mark.asyncio
async def test_qqofficial_send_record_resolves_to_tencent_silk(media_resolution):
    parsed = await QQOfficialMessageEvent._parse_to_qqofficial(
        MessageChain([Record(file="voice.amr", url="https://example.test/voice.amr")])
    )

    assert parsed[3] == media_resolution.path
    assert media_resolution.calls == [
        (
            "https://example.test/voice.amr",
            {"media_type": "audio", "default_suffix": ".wav"},
            {"target_format": "tencent_silk"},
        )
    ]


@pytest.mark.asyncio
async def test_misskey_audio_file_component_uses_media_resolver(media_resolution):
    record, part_text = await create_file_component(
        {
            "url": "https://example.test/voice.ogg",
            "name": "voice.ogg",
            "type": "audio/ogg",
        }
    )

    assert isinstance(record, Record)
    assert record.file == media_resolution.path
    assert record.url == media_resolution.path
    assert part_text == "音频[voice.ogg]"
    assert media_resolution.calls == [
        (
            "https://example.test/voice.ogg",
            {"media_type": "audio", "default_suffix": ".wav"},
            {"target_format": "wav"},
        )
    ]
