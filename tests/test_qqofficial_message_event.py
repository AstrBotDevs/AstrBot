from pathlib import Path

import pytest

from astrbot.core.message.components import Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)


def _wav_header() -> bytes:
    return b"RIFF\x00\x00\x00\x00WAVEfmt "


@pytest.mark.asyncio
async def test_parse_to_qqofficial_converts_non_wav_record_before_silk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_path = tmp_path / "voice.mp3"
    source_path.write_bytes(b"ID3fake-mp3")
    converted_paths: list[Path] = []

    async def fake_convert_audio_to_wav(audio_path: str, output_path: str | None = None):
        assert audio_path == str(source_path)
        assert output_path is not None
        converted_path = Path(output_path)
        converted_path.write_bytes(_wav_header())
        converted_paths.append(converted_path)
        return output_path

    async def fake_wav_to_tencent_silk(wav_path: str, silk_path: str):
        assert converted_paths
        assert wav_path == str(converted_paths[0])
        Path(silk_path).write_bytes(b"fake-silk")
        return 1200

    monkeypatch.setattr(
        "astrbot.core.platform.sources.qqofficial.qqofficial_message_event.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.qqofficial.qqofficial_message_event.convert_audio_to_wav",
        fake_convert_audio_to_wav,
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.qqofficial.qqofficial_message_event.wav_to_tencent_silk",
        fake_wav_to_tencent_silk,
    )

    result = await QQOfficialMessageEvent._parse_to_qqofficial(
        MessageChain([Record.fromFileSystem(str(source_path))])
    )

    assert converted_paths
    assert not converted_paths[0].exists()
    assert result[3] is not None
    assert str(result[3]).endswith(".silk")


@pytest.mark.asyncio
async def test_parse_to_qqofficial_skips_conversion_for_wav_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_path = tmp_path / "voice.wav"
    source_path.write_bytes(_wav_header())
    conversions: list[tuple[str, str | None]] = []

    async def fake_convert_audio_to_wav(audio_path: str, output_path: str | None = None):
        conversions.append((audio_path, output_path))
        return output_path or audio_path

    async def fake_wav_to_tencent_silk(wav_path: str, silk_path: str):
        assert wav_path == str(source_path)
        Path(silk_path).write_bytes(b"fake-silk")
        return 800

    monkeypatch.setattr(
        "astrbot.core.platform.sources.qqofficial.qqofficial_message_event.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.qqofficial.qqofficial_message_event.convert_audio_to_wav",
        fake_convert_audio_to_wav,
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.qqofficial.qqofficial_message_event.wav_to_tencent_silk",
        fake_wav_to_tencent_silk,
    )

    result = await QQOfficialMessageEvent._parse_to_qqofficial(
        MessageChain([Record.fromFileSystem(str(source_path))])
    )

    assert conversions == []
    assert result[3] is not None
    assert str(result[3]).endswith(".silk")
