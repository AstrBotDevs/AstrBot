import wave
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Record
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.platform.sources.slack.slack_event import SlackMessageEvent


@pytest.fixture
def audio_path(tmp_path):
    path = tmp_path / "speech.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 160)
    return path


@pytest.fixture
def slack_event(monkeypatch):
    monkeypatch.setattr(AstrMessageEvent, "send", AsyncMock())
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.group_id = "C123"
    message.sender = MessageMember(user_id="U123", nickname="Tester")
    message.message = []
    client = AsyncMock()
    client.files_upload_v2.return_value = {"ok": True}
    return SlackMessageEvent(
        "test",
        message,
        PlatformMetadata(name="slack", id="slack", description="Slack"),
        "C123",
        client,
    )


@pytest.mark.asyncio
async def test_slack_tts_uploads_audio_without_empty_messages(slack_event, audio_path):
    client = slack_event.web_client
    original = audio_path.read_bytes()

    await slack_event.send(
        MessageChain([Record(file=str(audio_path), text="Speech test.")])
    )

    client.files_upload_v2.assert_awaited_once_with(
        file=original, filename="speech.wav", channel="C123"
    )
    client.chat_postMessage.assert_not_awaited()
    assert audio_path.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("dual_output", [False, True])
async def test_slack_tts_upload_failure_preserves_source_text(
    slack_event, audio_path, monkeypatch, dual_output
):
    client = slack_event.web_client
    client.files_upload_v2.side_effect = RuntimeError("upload failed")
    chain = [Record(file=str(audio_path), text="Speech test.")]
    if dual_output:
        chain.append(Plain("Speech test."))
    slack_event.set_result(MessageEventResult(chain=chain))
    stage = RespondStage()
    stage.platform_settings = {}
    stage.enable_seg = False
    monkeypatch.setattr(
        "astrbot.core.pipeline.respond.stage.call_event_hook",
        AsyncMock(return_value=False),
    )

    await stage.process(slack_event)

    client.files_upload_v2.assert_awaited_once()
    client.chat_postMessage.assert_awaited_once()
    payload = client.chat_postMessage.await_args.kwargs
    assert payload["channel"] == "C123"
    assert payload["blocks"][0]["text"]["text"] == "Speech test."


@pytest.mark.asyncio
async def test_slack_tts_block_failure_retries_source_text(slack_event, audio_path):
    client = slack_event.web_client
    client.files_upload_v2.side_effect = RuntimeError("upload failed")
    client.chat_postMessage.side_effect = [
        RuntimeError("blocks rejected"),
        {"ok": True},
    ]

    await slack_event.send(
        MessageChain([Record(file=str(audio_path), text="Speech test.")])
    )

    client.files_upload_v2.assert_awaited_once()
    assert client.chat_postMessage.await_count == 2
    assert client.chat_postMessage.await_args.kwargs == {
        "channel": "C123",
        "text": "Speech test.",
    }
