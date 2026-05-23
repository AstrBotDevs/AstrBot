import base64
from pathlib import Path

import pytest

import astrbot.core.message.components as components
from astrbot.core.message.components import Record


@pytest.mark.asyncio
async def test_record_convert_to_file_path_prefers_url_when_file_is_name(
    monkeypatch,
    tmp_path,
):
    calls: list[tuple[str, Path]] = []
    audio_bytes = b"audio-content"
    audio_url = "http://napcat.local/nt_data/Ptt/2026-04/Ori/voice.amr"

    async def fake_download_file(url: str, path: str, *_, **__) -> None:
        target = Path(path)
        calls.append((url, target))
        target.write_bytes(audio_bytes)

    monkeypatch.setattr(components, "download_file", fake_download_file)
    monkeypatch.setattr(components, "get_astrbot_temp_path", lambda: str(tmp_path))

    record = Record(file="voice.amr", url=audio_url)

    file_path = Path(await record.convert_to_file_path())

    assert file_path.read_bytes() == audio_bytes
    assert file_path.suffix == ".amr"
    assert calls == [(audio_url, file_path)]


@pytest.mark.asyncio
async def test_record_convert_to_base64_prefers_url_when_file_is_name(
    monkeypatch,
    tmp_path,
):
    audio_bytes = b"audio-content"
    audio_url = "http://napcat.local/nt_data/Ptt/2026-04/Ori/voice.amr"

    async def fake_download_file(url: str, path: str, *_, **__) -> None:
        assert url == audio_url
        Path(path).write_bytes(audio_bytes)

    monkeypatch.setattr(components, "download_file", fake_download_file)
    monkeypatch.setattr(components, "get_astrbot_temp_path", lambda: str(tmp_path))

    record = Record(file="voice.amr", url=audio_url)

    assert await record.convert_to_base64() == base64.b64encode(audio_bytes).decode()


@pytest.mark.asyncio
async def test_record_convert_to_file_path_prefers_base64_url_when_file_is_name(
    monkeypatch,
    tmp_path,
):
    audio_bytes = b"audio-content"
    audio_url = f"base64://{base64.b64encode(audio_bytes).decode()}"

    monkeypatch.setattr(components, "get_astrbot_temp_path", lambda: str(tmp_path))

    record = Record(file="voice.amr", url=audio_url)

    file_path = Path(await record.convert_to_file_path())

    assert file_path.read_bytes() == audio_bytes
    assert file_path.suffix == ".amr"


@pytest.mark.asyncio
async def test_record_convert_to_base64_prefers_base64_url_when_file_is_name():
    audio_bytes = b"audio-content"
    audio_base64 = base64.b64encode(audio_bytes).decode()

    record = Record(file="voice.amr", url=f"base64://{audio_base64}")

    assert await record.convert_to_base64() == audio_base64
