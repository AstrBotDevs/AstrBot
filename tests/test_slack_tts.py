import wave
from functools import partial
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Record
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter
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


@pytest.fixture(params=["event", "session"])
def slack_sender(request, slack_event, monkeypatch):
    if request.param == "event":
        return slack_event.send, slack_event.web_client
    monkeypatch.setattr(Platform, "send_by_session", AsyncMock())
    adapter = object.__new__(SlackAdapter)
    adapter.web_client = slack_event.web_client
    session = MessageSesion(
        platform_name="slack",
        message_type=MessageType.GROUP_MESSAGE,
        session_id="C123",
    )
    return partial(adapter.send_by_session, session), adapter.web_client


@pytest.mark.asyncio
async def test_slack_tts_uploads_audio_without_empty_messages(slack_sender, audio_path):
    send, client = slack_sender
    original = audio_path.read_bytes()

    await send(
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
async def test_slack_tts_block_failure_retries_source_text(slack_sender, audio_path):
    send, client = slack_sender
    client.files_upload_v2.side_effect = RuntimeError("upload failed")
    client.chat_postMessage.side_effect = [
        RuntimeError("blocks rejected"),
        {"ok": True},
    ]

    await send(
        MessageChain([Record(file=str(audio_path), text="Speech test.")])
    )

    client.files_upload_v2.assert_awaited_once()
    assert client.chat_postMessage.await_count == 2
    assert client.chat_postMessage.await_args_list[0].kwargs == {
        "channel": "C123",
        "text": "",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": "Speech test."}}
        ],
    }
    assert client.chat_postMessage.await_args.kwargs == {
        "channel": "C123",
        "text": "Speech test.",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "upload", "blocks"])
async def test_slack_tts_preserves_mixed_message_order(
    slack_sender, audio_path, failure
):
    send, client = slack_sender
    if failure == "upload":
        client.files_upload_v2.side_effect = RuntimeError("upload failed")
    elif failure == "blocks":
        client.chat_postMessage.side_effect = [
            {"ok": True},
            RuntimeError("blocks rejected"),
            {"ok": True},
        ]

    await send(
        MessageChain(
            [
                Plain("Speech test."),
                Record(file=str(audio_path), text="Speech test."),
                Plain("After."),
            ]
        )
    )

    expected_calls = ["chat_postMessage", "files_upload_v2", "chat_postMessage"]
    if failure == "blocks":
        expected_calls.append("chat_postMessage")
        assert client.chat_postMessage.await_args.kwargs == {
            "channel": "C123", "text": "After."
        }
    assert [call[0] for call in client.mock_calls] == expected_calls
    assert [
        call.kwargs["blocks"][0]["text"]["text"]
        for call in client.chat_postMessage.await_args_list[:2]
    ] == ["Speech test.", "After."]
