import base64
import io
import wave
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiocqhttp import Event

from astrbot.core.message.components import Record
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)


def _record_event(data: dict) -> Event:
    event = Event.from_payload(
        {
            "post_type": "message",
            "message_type": "private",
            "sub_type": "friend",
            "message_id": 100,
            "user_id": 200,
            "self_id": 300,
            "sender": {"user_id": 200, "nickname": "tester"},
            "message": [{"type": "record", "data": data}],
            "raw_message": "",
            "time": 1,
            "font": 0,
        }
    )
    assert event is not None
    return event


def _adapter(bot: AsyncMock) -> AiocqhttpAdapter:
    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    adapter.bot = bot
    return adapter


@pytest.mark.asyncio
async def test_bare_record_file_is_resolved_through_onebot_get_record(tmp_path):
    converted_file = tmp_path / "voice.wav"
    with wave.open(str(converted_file), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00\x00")
    bot = AsyncMock()
    bot.call_action.return_value = {"file": str(converted_file)}
    event = _record_event({"file": "voice.amr"})

    message = await _adapter(bot)._convert_handle_message_event(event)

    assert len(message.message) == 1
    record = message.message[0]
    assert isinstance(record, Record)
    assert record.file == str(converted_file)
    assert await record.convert_to_file_path() == str(converted_file.resolve())
    assert event.message[0]["data"]["file"] == "voice.amr"
    bot.call_action.assert_awaited_once_with(
        action="get_record",
        file="voice.amr",
        out_format="wav",
        self_id=300,
    )


@pytest.mark.asyncio
async def test_record_with_legacy_bare_base64_does_not_call_get_record():
    audio_buffer = io.BytesIO()
    with wave.open(audio_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00\x00")
    encoded_audio = base64.b64encode(audio_buffer.getvalue()).decode()
    bot = AsyncMock()

    message = await _adapter(bot)._convert_handle_message_event(
        _record_event({"file": encoded_audio})
    )

    record = message.message[0]
    assert isinstance(record, Record)
    assert record.file == encoded_audio
    resolved_path = Path(await record.convert_to_file_path())
    try:
        resolved_bytes = resolved_path.read_bytes()
        assert resolved_bytes[:4] == b"RIFF"
        assert resolved_bytes[8:12] == b"WAVE"
    finally:
        resolved_path.unlink(missing_ok=True)
    bot.call_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_with_url_does_not_call_get_record():
    bot = AsyncMock()
    data = {
        "file": " voice.amr ",
        "url": " https://example.test/voice.amr ",
    }

    message = await _adapter(bot)._convert_handle_message_event(_record_event(data))

    record = message.message[0]
    assert isinstance(record, Record)
    assert record.file == "voice.amr"
    assert record.url == "https://example.test/voice.amr"
    assert data["file"] == " voice.amr "
    assert data["url"] == " https://example.test/voice.amr "
    bot.call_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_record_failure_preserves_original_record_segment():
    bot = AsyncMock()
    bot.call_action.side_effect = RuntimeError("get_record unavailable")

    message = await _adapter(bot)._convert_handle_message_event(
        _record_event({"file": "voice.amr"})
    )

    assert len(message.message) == 1
    record = message.message[0]
    assert isinstance(record, Record)
    assert record.file == "voice.amr"
    bot.call_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_inaccessible_get_record_path_preserves_original_record_segment():
    bot = AsyncMock()
    bot.call_action.return_value = {"file": "/remote/voice.wav"}

    message = await _adapter(bot)._convert_handle_message_event(
        _record_event({"file": "voice.amr"})
    )

    record = message.message[0]
    assert isinstance(record, Record)
    assert record.file == "voice.amr"
    bot.call_action.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("source_field", ["path", "url"])
async def test_record_with_existing_source_field_does_not_call_get_record(source_field):
    bot = AsyncMock()

    message = await _adapter(bot)._convert_handle_message_event(
        _record_event(
            {
                "file": "voice.amr",
                source_field: "/remote/voice.amr",
            }
        )
    )

    record = message.message[0]
    assert isinstance(record, Record)
    assert record.file == "voice.amr"
    bot.call_action.assert_not_awaited()
