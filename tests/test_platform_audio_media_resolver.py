import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Record
from astrbot.core.platform.sources.lark import lark_adapter
from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter
from astrbot.core.platform.sources.line import line_adapter
from astrbot.core.platform.sources.line.line_adapter import LinePlatformAdapter
from astrbot.core.platform.sources.misskey import misskey_utils
from astrbot.core.platform.sources.misskey.misskey_utils import create_file_component
from astrbot.core.platform.sources.qqofficial import (
    qqofficial_message_event,
    qqofficial_platform_adapter,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)

WAV_PATH = "/tmp/astrbot-platform-audio.wav"


class FakeMediaResolver:
    calls = []

    def __init__(self, media_ref: str, **kwargs) -> None:
        self.media_ref = media_ref
        self.kwargs = kwargs
        self.calls.append((media_ref, kwargs))

    async def to_path(self, **kwargs) -> str:
        self.calls[-1] = (*self.calls[-1], kwargs)
        return WAV_PATH


def _patch_resolver(monkeypatch, module) -> None:
    FakeMediaResolver.calls = []
    monkeypatch.setattr(module, "MediaResolver", FakeMediaResolver)


@pytest.mark.asyncio
async def test_line_audio_component_uses_media_resolver_for_external_url(monkeypatch):
    _patch_resolver(monkeypatch, line_adapter)
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
    assert record.file == WAV_PATH
    assert record.url == WAV_PATH
    assert FakeMediaResolver.calls == [
        (
            "https://example.test/voice.m4a",
            {"media_type": "audio", "default_suffix": ".wav"},
            {"target_format": "wav"},
        )
    ]


@pytest.mark.asyncio
async def test_lark_audio_component_uses_media_resolver_after_download(monkeypatch):
    _patch_resolver(monkeypatch, lark_adapter)
    adapter = LarkPlatformAdapter.__new__(LarkPlatformAdapter)

    async def fake_download_file_resource_to_temp(**kwargs):
        assert kwargs["message_type"] == "audio"
        return "/tmp/lark-source.opus"

    monkeypatch.setattr(
        adapter,
        "_download_file_resource_to_temp",
        fake_download_file_resource_to_temp,
    )

    records = await adapter._parse_message_components(
        message_id="msg-1",
        message_type="audio",
        content={"file_key": "file-key"},
        at_map={},
    )

    assert len(records) == 1
    assert isinstance(records[0], Record)
    assert records[0].file == WAV_PATH
    assert records[0].url == WAV_PATH
    assert FakeMediaResolver.calls == [
        (
            "/tmp/lark-source.opus",
            {"media_type": "audio", "default_suffix": ".wav"},
            {"target_format": "wav"},
        )
    ]


@pytest.mark.asyncio
async def test_qqofficial_audio_attachment_uses_media_resolver(monkeypatch):
    _patch_resolver(monkeypatch, qqofficial_platform_adapter)

    record = await QQOfficialPlatformAdapter._prepare_audio_attachment(
        "https://example.test/voice.amr",
        "voice.amr",
    )

    assert isinstance(record, Record)
    assert record.file == WAV_PATH
    assert record.url == WAV_PATH
    assert FakeMediaResolver.calls == [
        (
            "https://example.test/voice.amr",
            {"media_type": "audio", "default_suffix": ".amr"},
            {"target_format": "wav"},
        )
    ]


@pytest.mark.asyncio
async def test_qqofficial_send_record_resolves_to_tencent_silk(monkeypatch):
    _patch_resolver(monkeypatch, qqofficial_message_event)

    parsed = await QQOfficialMessageEvent._parse_to_qqofficial(
        MessageChain([Record(file="voice.amr", url="https://example.test/voice.amr")])
    )

    assert parsed[3] == WAV_PATH
    assert FakeMediaResolver.calls == [
        (
            "https://example.test/voice.amr",
            {"media_type": "audio", "default_suffix": ".wav"},
            {"target_format": "tencent_silk"},
        )
    ]


@pytest.mark.asyncio
async def test_misskey_audio_file_component_uses_media_resolver(monkeypatch):
    _patch_resolver(monkeypatch, misskey_utils)

    record, part_text = await create_file_component(
        {
            "url": "https://example.test/voice.ogg",
            "name": "voice.ogg",
            "type": "audio/ogg",
        }
    )

    assert isinstance(record, Record)
    assert record.file == WAV_PATH
    assert record.url == WAV_PATH
    assert part_text == "音频[voice.ogg]"
    assert FakeMediaResolver.calls == [
        (
            "https://example.test/voice.ogg",
            {"media_type": "audio", "default_suffix": ".wav"},
            {"target_format": "wav"},
        )
    ]
