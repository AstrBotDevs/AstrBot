from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.message.components import Plain, Record, Reply
from astrbot.core.pipeline.preprocess_stage.stage import PreProcessStage


def _make_stage(stt_provider: AsyncMock) -> PreProcessStage:
    stage = PreProcessStage()
    stage.config = {}
    stage.platform_settings = {}
    stage.stt_settings = {"enable": True}
    stage.plugin_manager = SimpleNamespace(
        context=SimpleNamespace(get_using_stt_provider=lambda _: stt_provider)
    )
    return stage


def _make_event(messages: list) -> MagicMock:
    event = MagicMock()
    event.get_platform_name.return_value = "test"
    event.is_at_or_wake_command = False
    event.get_messages.return_value = messages
    event.unified_msg_origin = "test:friend:test"
    event.message_str = ""
    event.message_obj.message_str = ""
    return event


@pytest.mark.asyncio
async def test_failed_audio_conversion_is_not_sent_to_stt(monkeypatch):
    failed_record = Record(file="failed.amr")
    valid_record = Record(file="valid.wav")
    messages = [failed_record, valid_record]
    stt_provider = AsyncMock()
    stt_provider.get_text.return_value = "transcribed"

    async def convert_to_file_path(record):
        return record.file

    async def convert_to_wav(path):
        if path == "failed.amr":
            raise RuntimeError("ffmpeg not found")
        return path

    monkeypatch.setattr(Record, "convert_to_file_path", convert_to_file_path)
    monkeypatch.setattr(
        "astrbot.core.pipeline.preprocess_stage.stage.ensure_wav",
        convert_to_wav,
    )

    await _make_stage(stt_provider).process(_make_event(messages))

    assert messages[0] is failed_record
    assert isinstance(messages[1], Plain)
    assert messages[1].text == "transcribed"
    stt_provider.get_text.assert_awaited_once_with(audio_url="valid.wav")


@pytest.mark.asyncio
async def test_failed_reply_audio_conversion_is_not_sent_to_stt(monkeypatch):
    failed_record = Record(file="failed.amr")
    reply = Reply(id="reply-id", chain=[failed_record])
    stt_provider = AsyncMock()

    async def convert_to_file_path(record):
        return record.file

    async def convert_to_wav(_):
        raise RuntimeError("ffmpeg not found")

    monkeypatch.setattr(Record, "convert_to_file_path", convert_to_file_path)
    monkeypatch.setattr(
        "astrbot.core.pipeline.preprocess_stage.stage.ensure_wav",
        convert_to_wav,
    )

    await _make_stage(stt_provider).process(_make_event([reply]))

    assert reply.chain == [failed_record]
    stt_provider.get_text.assert_not_awaited()
