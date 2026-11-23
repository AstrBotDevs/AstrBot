"""Exercise public Telegram delivery through real component and chunk policies."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest, NetworkError, TimedOut

from astrbot.api.message_components import ActionRow, Button, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.telegram import tg_event


@pytest.fixture
def client():
    return SimpleNamespace(send_chat_action=AsyncMock(), send_message=AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("delivery unknown"),
        TimedOut("delivery unknown"),
        NetworkError("delivery unknown"),
        ValueError("response decoding failed"),
        asyncio.CancelledError(),
    ],
)
async def test_public_send_preserves_unknown_outcome_without_replay(
    client, monkeypatch, error
):
    monkeypatch.setattr(tg_event.telegramify_markdown, "markdownify", lambda text: text)
    client.send_message.side_effect = error

    with pytest.raises(type(error)) as caught:
        await tg_event.TelegramPlatformEvent.send_with_client(
            client, MessageChain([Plain("message")]), "42#7"
        )

    assert caught.value is error
    client.send_message.assert_awaited_once_with(
        text="message", parse_mode="MarkdownV2", chat_id="42", message_thread_id=7
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("formatter_fails", [False, True])
async def test_public_chunks_preserve_text_and_attach_keyboard_only_to_final_chunk(
    client, monkeypatch, formatter_fails
):
    monkeypatch.setattr(tg_event.TelegramPlatformEvent, "MAX_MESSAGE_LENGTH", 4)

    def format_text(text):
        if formatter_fails:
            raise RuntimeError("formatter failed before dispatch")
        return text

    monkeypatch.setattr(tg_event.telegramify_markdown, "markdownify", format_text)
    row = ActionRow(
        buttons=[
            Button(
                id="docs",
                label="Docs",
                action=Button.UrlAction(url="https://example.invalid"),
            )
        ]
    )
    await tg_event.TelegramPlatformEvent.send_with_client(
        client, MessageChain([Plain("abcdefghij"), row]), "42#7"
    )

    calls = [call.kwargs for call in client.send_message.await_args_list]
    assert [call["text"] for call in calls] == ["abcd", "efgh", "ij"]
    assert all(
        call["chat_id"] == "42" and call["message_thread_id"] == 7 for call in calls
    )
    assert all("reply_markup" not in call for call in calls[:-1])
    assert (
        calls[-1]["reply_markup"].inline_keyboard[0][0].url == "https://example.invalid"
    )
    assert all(("parse_mode" not in call) == formatter_fails for call in calls)


@pytest.mark.asyncio
async def test_public_markdown_rejection_retries_original_text_once(
    client, monkeypatch
):
    monkeypatch.setattr(
        tg_event.telegramify_markdown, "markdownify", lambda text: "escaped"
    )
    client.send_message.side_effect = [BadRequest("invalid markdown"), None]

    await tg_event.TelegramPlatformEvent.send_with_client(
        client, MessageChain([Plain("original")]), "42"
    )

    assert [call.kwargs for call in client.send_message.await_args_list] == [
        {"text": "escaped", "parse_mode": "MarkdownV2", "chat_id": "42"},
        {"text": "original", "chat_id": "42"},
    ]
